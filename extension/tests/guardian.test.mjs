// @ts-check
/** Kiểm thử Guardian mode (không mạng, không trình duyệt): thử thách–mã, khóa, hết hạn, chỉnh giờ, chính sách ký, fail-closed. */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

import {
  POLICY_CONTEXT, computeCode, fromBase64Url, newNonce, normalizeDomain, normalizeNonce, toBase32, toBase64Url,
} from "../src/guardian/codec.js";
import {
  CLOCK_TOLERANCE_MS, DEFAULT_TTL_MS, Guardian, LOCK_STEPS_MS, MAX_ATTEMPTS, POLICY_KEY, resolveConfig, STATE_KEY,
} from "../src/guardian/guardian.js";
import { REPO_DIR } from "./helpers.mjs";

const vectors = JSON.parse(await readFile(path.join(REPO_DIR, "tests", "data", "guardian_vectors.json"), "utf-8"));
const SECRET = fromBase64Url(vectors.hmac_secret);
const encoder = new TextEncoder();

/** Kho lưu trữ giả (``chrome.storage.local``/``session``). */
function memoryArea() {
  /** @type {Record<string, any>} */
  const items = {};
  return {
    items,
    get: async (/** @type {string} */ key) => (key in items ? { [key]: structuredClone(items[key]) } : {}),
    set: async (/** @type {Record<string, unknown>} */ values) => { Object.assign(items, structuredClone(values)); },
  };
}

/** Cặp khóa Ed25519 thử nghiệm (WebCrypto) để ký chính sách trong test. */
async function makeKeyPair() {
  const pair = /** @type {CryptoKeyPair} */ (await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]));
  const publicKey = toBase64Url(new Uint8Array(await crypto.subtle.exportKey("raw", pair.publicKey)));
  return {
    publicKey,
    /** @param {Record<string, unknown>} fields */
    async sign(fields) {
      const payload = JSON.stringify(fields);
      const signature = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, pair.privateKey, encoder.encode(POLICY_CONTEXT + payload)));
      return { payload, signature: toBase64Url(signature) };
    },
  };
}

/**
 * Dựng Guardian với managed/local/session/giờ giả.
 * @param {{managed?: Record<string, unknown> | null, pubkey?: string}} [options]
 */
async function setup(options = {}) {
  const keys = await makeKeyPair();
  const managed = options.managed === undefined
    ? { guardian_enabled: true, guardian_public_key: options.pubkey ?? keys.publicKey, guardian_secret: vectors.hmac_secret, min_policy_version: 0 }
    : options.managed;
  const env = {
    managed, local: memoryArea(), session: memoryArea(), clock: 1_700_000_000_000,
    guardian: /** @type {Guardian} */ (/** @type {unknown} */ (null)),
  };
  env.guardian = new Guardian({
    readManaged: async () => env.managed, local: env.local, session: env.session, now: () => env.clock,
  });
  return { env, keys };
}

const URL_A = "https://vietcombank-xacthuc.top/login";
const URL_B = "https://momo-hoantien.vip/nhan-qua";

/**
 * Phát thử thách và trả (thử thách + mã đúng).
 * @param {Guardian} guardian
 * @param {string} url
 * @param {string} domain
 */
async function challenge(guardian, url, domain) {
  const c = await guardian.issue({ url, domain });
  assert.equal(c.status, "challenge");
  if (c.status !== "challenge") throw new Error("không phát được thử thách");
  return { ...c, code: await computeCode(SECRET, c.domain, c.nonce) };
}

/** Mã chắc chắn sai (khác mã đúng). */
const wrong = (/** @type {string} */ code) => String((Number(code) + 1) % 1_000_000).padStart(6, "0");

test("vector chung với Python: mã mở khóa, base32, chữ ký chính sách Ed25519", async () => {
  for (const v of vectors.codes) assert.equal(await computeCode(SECRET, v.domain, v.nonce), v.code, v.message);
  for (const v of vectors.nonce_bytes) assert.equal(toBase32(Uint8Array.from(Buffer.from(v.hex, "hex"))), v.base32);
  const config = await resolveConfig(
    { guardian_enabled: true, guardian_public_key: vectors.policy.public_key, guardian_secret: vectors.hmac_secret, min_policy_version: 7 },
    { payload: vectors.policy.payload, signature: vectors.policy.signature });
  assert.equal(config.policyProblem, null);
  assert.equal(config.policy.version, 7);
  assert.deepEqual(config.policy.allowDomains, ["vietcombank.com.vn"]);
  assert.equal(config.policy.ttlMs, 300_000);
  assert.deepEqual([...config.policy.requireLevels].sort(), ["BLOCKED", "HIGH"]);
});

test("nonce: 40 bit ngẫu nhiên dạng base32 8 ký tự; chuẩn hóa chấp nhận gạch và chữ thường", () => {
  const n = newNonce();
  assert.match(n, /^[A-Z2-7]{8}$/);
  assert.notEqual(newNonce(), newNonce());
  assert.equal(normalizeNonce("k7qf-3mzd"), "K7QF3MZD");
  assert.equal(normalizeNonce("K7QF 3MZD"), "K7QF3MZD");
  assert.equal(normalizeNonce("K7QF-3MZ"), null);
  assert.equal(normalizeNonce("K7QF-3M10"), null);
  assert.equal(normalizeDomain("Example.COM."), "example.com");
  assert.equal(normalizeDomain("a|b.com"), null);
});

test("mã đúng mở đúng link; thử thách bị xóa ngay nên dùng lại bị từ chối", async () => {
  const { env } = await setup();
  const c = await challenge(env.guardian, URL_A, "vietcombank-xacthuc.top");
  assert.equal(c.attemptsLeft, MAX_ATTEMPTS);
  assert.match(c.nonceText, /^[A-Z2-7]{4}-[A-Z2-7]{4}$/);
  assert.deepEqual(await env.guardian.submit({ id: c.id, code: c.code, url: URL_A }), { ok: true });
  const again = await env.guardian.submit({ id: c.id, code: c.code, url: URL_A });
  assert.equal(again.ok, false);
  assert.equal(/** @type {any} */ (again).reason, "gone");
  assert.equal(Object.keys(env.local.items[STATE_KEY].challenges).length, 0);
  // Mã cũ không mở được link thử thách mới (nonce mới).
  const next = await challenge(env.guardian, URL_A, "vietcombank-xacthuc.top");
  assert.notEqual(next.nonce, c.nonce);
  const stale = await env.guardian.submit({ id: next.id, code: c.code, url: URL_A });
  assert.equal(/** @type {any} */ (stale).reason, "wrong");
});

test("mã đúng của tên miền khác bị từ chối; thử thách chỉ mở đúng URL của nó", async () => {
  const { env } = await setup();
  const a = await challenge(env.guardian, URL_A, "vietcombank-xacthuc.top");
  const b = await challenge(env.guardian, URL_B, "momo-hoantien.vip");
  const crossed = await env.guardian.submit({ id: a.id, code: b.code, url: URL_A });
  assert.deepEqual([crossed.ok, /** @type {any} */ (crossed).reason, /** @type {any} */ (crossed).attemptsLeft], [false, "wrong", 4]);
  // Mã của chính tên miền A nhưng gửi kèm URL khác → không khớp URL, không mở.
  const mismatch = await env.guardian.submit({ id: a.id, code: a.code, url: URL_B });
  assert.equal(/** @type {any} */ (mismatch).reason, "mismatch");
  // Cùng tên miền, nonce khác: mã của thử thách này không dùng được cho thử thách kia (cả hai cùng domain).
  const a2 = await challenge(env.guardian, "https://vietcombank-xacthuc.top/khac", "vietcombank-xacthuc.top");
  const cross2 = await env.guardian.submit({ id: a2.id, code: a.code, url: "https://vietcombank-xacthuc.top/khac" });
  assert.equal(/** @type {any} */ (cross2).reason, "wrong");
  assert.equal((await env.guardian.submit({ id: b.id, code: b.code, url: URL_B })).ok, true);
});

test("sai định dạng không tốn lượt; quá 5 lần sai thì hủy thử thách và khóa tăng dần 30 giây, 2 phút, 10 phút", async () => {
  const { env } = await setup();
  let c = await challenge(env.guardian, URL_A, "vietcombank-xacthuc.top");
  const bad = await env.guardian.submit({ id: c.id, code: "12ab", url: URL_A });
  assert.deepEqual([/** @type {any} */ (bad).reason, /** @type {any} */ (bad).attemptsLeft], ["format", 5]);
  for (let i = 1; i < MAX_ATTEMPTS; i++) {
    const r = await env.guardian.submit({ id: c.id, code: wrong(c.code), url: URL_A });
    assert.deepEqual([/** @type {any} */ (r).reason, /** @type {any} */ (r).attemptsLeft], ["wrong", MAX_ATTEMPTS - i]);
  }
  const last = await env.guardian.submit({ id: c.id, code: wrong(c.code), url: URL_A });
  assert.equal(/** @type {any} */ (last).reason, "destroyed");
  assert.equal(/** @type {any} */ (last).lockedUntil, env.clock + LOCK_STEPS_MS[0]);
  // Thử thách đã hủy: mã ĐÚNG cũng vô dụng; đang khóa thì không phát thử thách mới.
  assert.equal(/** @type {any} */ (await env.guardian.submit({ id: c.id, code: c.code, url: URL_A })).reason, "gone");
  assert.equal((await env.guardian.issue({ url: URL_A, domain: "vietcombank-xacthuc.top" })).status, "locked");
  // Hết 30 giây: được thử lại, lần khóa kế tiếp 2 phút rồi 10 phút (và giữ 10 phút).
  for (const [waited, next] of [[0, 1], [1, 2], [2, 2]]) {
    env.clock += LOCK_STEPS_MS[waited] + 1;
    c = await challenge(env.guardian, URL_A, "vietcombank-xacthuc.top");
    let r;
    for (let i = 0; i < MAX_ATTEMPTS; i++) r = await env.guardian.submit({ id: c.id, code: wrong(c.code), url: URL_A });
    assert.equal(/** @type {any} */ (r).lockedUntil, env.clock + LOCK_STEPS_MS[next]);
  }
  assert.ok(/** @type {any} */ ((await env.guardian.status()).warnings).length > 0);
});

test("thử thách hết hạn sau 10 phút; trượt trong lúc khóa không được tính là mở", async () => {
  const { env } = await setup();
  const c = await challenge(env.guardian, URL_A, "vietcombank-xacthuc.top");
  assert.equal(c.expiresAt, env.clock + DEFAULT_TTL_MS);
  env.clock += DEFAULT_TTL_MS - 1;
  const lateButOk = await challenge(env.guardian, URL_B, "momo-hoantien.vip"); // phát mới giữa chừng
  assert.equal((await env.guardian.submit({ id: lateButOk.id, code: lateButOk.code, url: URL_B })).ok, true);
  env.clock += 2;
  const expired = await env.guardian.submit({ id: c.id, code: c.code, url: URL_A });
  assert.deepEqual([expired.ok, /** @type {any} */ (expired).reason], [false, "gone"]);
});

test("lùi giờ quá 5 phút hủy mọi thử thách và ghi cảnh báo; lùi nhỏ thì không", async () => {
  const { env } = await setup();
  const a = await challenge(env.guardian, URL_A, "vietcombank-xacthuc.top");
  env.clock -= CLOCK_TOLERANCE_MS - 1000; // lùi 4 phút 59 giây: chấp nhận
  assert.equal((await env.guardian.submit({ id: a.id, code: wrong(a.code), url: URL_A })).ok, false);
  assert.equal(/** @type {any} */ ((await env.guardian.status()).warnings).length, 0);
  const b = await challenge(env.guardian, URL_B, "momo-hoantien.vip");
  env.clock -= 10 * 60_000; // tổng cộng lùi ~15 phút để kéo dài thử thách
  const r = await env.guardian.submit({ id: b.id, code: b.code, url: URL_B });
  assert.deepEqual([r.ok, /** @type {any} */ (r).reason], [false, "gone"]);
  const status = /** @type {any} */ (await env.guardian.status());
  assert.equal(status.pending, 0);
  assert.match(status.warnings.at(-1).msg, /lùi/);
});

test("trình duyệt khởi động lại (storage.session mất) hoặc kho cục bộ bị xóa thì mọi thử thách mất", async () => {
  const { env } = await setup();
  const c = await challenge(env.guardian, URL_A, "vietcombank-xacthuc.top");
  env.session.items = /** @type {any} */ (undefined);
  for (const k of Object.keys(env.session.items ?? {})) delete env.session.items[k];
  const fresh = memoryArea();
  const restarted = new Guardian({ readManaged: async () => env.managed, local: env.local, session: fresh, now: () => env.clock });
  assert.equal(/** @type {any} */ (await restarted.submit({ id: c.id, code: c.code, url: URL_A })).reason, "gone");
  // Xóa bộ đếm (kho cục bộ) → thử thách cũng mất theo.
  const d = await challenge(env.guardian, URL_A, "vietcombank-xacthuc.top");
  delete env.local.items[STATE_KEY];
  assert.equal(/** @type {any} */ (await env.guardian.submit({ id: d.id, code: d.code, url: URL_A })).reason, "gone");
});

test("managed thiếu hoặc Guardian tắt: hành vi cũ không đổi (không cần xin phép)", async () => {
  for (const managed of [null, {}, { guardian_enabled: false, guardian_secret: vectors.hmac_secret }]) {
    const { env } = await setup({ managed });
    const config = await env.guardian.config();
    assert.equal(config.mode, "off");
    for (const level of ["WARN", "HIGH", "BLOCKED"]) assert.equal(Guardian.requires(config, level, "x.top"), false);
  }
  // Kẻ tấn công đặt cờ/khóa trong storage.local không có tác dụng gì.
  const { env } = await setup({ managed: {} });
  await env.local.set({ guardian_enabled: true, guardianPolicy: { payload: "{}", signature: "" }, guardian_secret: "x" });
  assert.equal((await env.guardian.config()).mode, "off");
});

test("managed đọc lỗi: dùng bản đọc tốt gần nhất, chưa từng có thì coi như tắt", async () => {
  const { env } = await setup();
  assert.equal((await env.guardian.config()).mode, "ok");
  const guardian = new Guardian({
    readManaged: async () => { throw new Error("không có schema"); }, local: env.local, session: env.session, now: () => env.clock,
  });
  assert.equal((await guardian.config()).mode, "off");
  guardian.lastManaged = env.managed;
  assert.equal((await guardian.config()).mode, "ok");
});

test("bật nhưng cấu hình managed hỏng (thiếu secret): vẫn bật, không ai mở khóa được (fail-closed)", async () => {
  const { env } = await setup({ managed: { guardian_enabled: true, guardian_public_key: "xx" } });
  const config = await env.guardian.config();
  assert.equal(config.mode, "misconfigured");
  assert.equal(Guardian.requires(config, "HIGH", "x.top"), true);
  assert.equal((await env.guardian.issue({ url: URL_A, domain: "x.top" })).status, "misconfigured");
  assert.equal(/** @type {any} */ (await env.guardian.submit({ id: "a", code: "123456", url: URL_A })).reason, "misconfigured");
});

test("chính sách ký hợp lệ được áp dụng (cho phép tên miền, thêm mức WARN, đổi hạn); BLOCKED không thể nới", async () => {
  const { env, keys } = await setup();
  const signed = await keys.sign({
    version: 3, require_levels: ["WARN"], allow_domains: ["Cho-phep.vn"], challenge_ttl_sec: 120,
  });
  assert.deepEqual(await env.guardian.importPolicy(JSON.stringify(signed)), { ok: true, version: 3 });
  const config = await env.guardian.config();
  assert.equal(config.policy.source, "signed");
  assert.equal(config.policy.ttlMs, 120_000);
  assert.equal(Guardian.requires(config, "WARN", "khac.top"), true);
  assert.equal(Guardian.requires(config, "HIGH", "khac.top"), false, "HIGH không có trong chính sách ký này");
  assert.equal(Guardian.requires(config, "WARN", "cho-phep.vn"), false, "tên miền luôn cho phép");
  assert.equal(Guardian.requires(config, "BLOCKED", "cho-phep.vn"), true, "BLOCKED luôn cần mã, kể cả tên miền trong danh sách cho phép");
  const c = await challenge(env.guardian, URL_A, "vietcombank-xacthuc.top");
  assert.equal(c.expiresAt, env.clock + 120_000);
});

test("chính sách chữ ký sai / thiếu / hỏng / version thấp hơn min: fail-closed (HIGH và BLOCKED cần mã, vẫn bật)", async () => {
  const { env, keys } = await setup();
  const attacker = await makeKeyPair();
  const loose = { version: 5, require_levels: ["BLOCKED"], allow_domains: ["vietcombank-xacthuc.top"] };
  const good = await keys.sign(loose);
  const strict = { HIGH: true, BLOCKED: true, WARN: false };
  const expectStrict = async (/** @type {string} */ why, /** @type {RegExp | null} */ problem) => {
    const config = await env.guardian.config();
    assert.equal(config.mode, "ok", why);
    assert.equal(config.policy.source, "managed-only", why);
    assert.deepEqual(config.policy.allowDomains, [], why);
    for (const [level, needed] of Object.entries(strict)) assert.equal(Guardian.requires(config, level, "vietcombank-xacthuc.top"), needed, `${why}/${level}`);
    if (problem) assert.match(String(config.policyProblem), problem, why);
    else assert.equal(config.policyProblem, null, why);
  };
  await env.local.set({ [POLICY_KEY]: good });
  assert.equal((await env.guardian.config()).policy.source, "signed"); // đối chứng: bản đúng được nhận

  await env.local.set({ [POLICY_KEY]: await attacker.sign(loose) });
  await expectStrict("ký bằng khóa của kẻ tấn công", /chữ ký/);
  await env.local.set({ [POLICY_KEY]: { payload: good.payload.replace("5", "6"), signature: good.signature } });
  await expectStrict("payload bị sửa sau khi ký", /chữ ký/);
  await env.local.set({ [POLICY_KEY]: { payload: good.payload, signature: "@@@" } });
  await expectStrict("chữ ký không phải base64", /base64/);
  await env.local.set({ [POLICY_KEY]: "rác" });
  await expectStrict("phong bì hỏng", /hỏng/);
  await env.local.set({ [POLICY_KEY]: await keys.sign({ version: 1, require_levels: ["TUY_Y"] }) });
  await expectStrict("cấu trúc sai (đã ký đúng)", /require_levels/);
  await env.local.set({ [POLICY_KEY]: await keys.sign({ version: 1, challenge_ttl_sec: 999999 }) });
  await expectStrict("hạn ngoài miền", /challenge_ttl_sec/);

  delete env.local.items[POLICY_KEY];
  await expectStrict("thiếu chính sách", null);

  // Hạ cấp/rollback: bản cũ có chữ ký hợp lệ nhưng version < min_policy_version.
  env.managed = { ...(/** @type {object} */ (env.managed)), min_policy_version: 6 };
  await env.local.set({ [POLICY_KEY]: good });
  await expectStrict("version 5 < min 6", /chống hạ cấp/);
  env.managed = { ...(/** @type {object} */ (env.managed)), min_policy_version: 5 };
  assert.equal((await env.guardian.config()).policy.source, "signed", "version == min thì nhận");
  // importPolicy cũng từ chối bản thấp phiên bản và bản sai chữ ký, không ghi đè bản đang có.
  env.managed = { ...(/** @type {object} */ (env.managed)), min_policy_version: 9 };
  assert.match(String((await env.guardian.importPolicy(JSON.stringify(good))).error), /chống hạ cấp/);
  assert.match(String((await env.guardian.importPolicy("không phải json")).error), /JSON/);
  assert.deepEqual(env.local.items[POLICY_KEY], good);
});

test("khóa công khai chỉ lấy từ managed: đặt khóa của kẻ tấn công vào storage.local không giúp ký được chính sách", async () => {
  const { env } = await setup();
  const attacker = await makeKeyPair();
  await env.local.set({ guardian_public_key: attacker.publicKey, guardianPublicKey: attacker.publicKey,
    [POLICY_KEY]: await attacker.sign({ version: 1, require_levels: ["BLOCKED"], allow_domains: ["vietcombank-xacthuc.top"] }) });
  const config = await env.guardian.config();
  assert.equal(config.policy.source, "managed-only");
  assert.equal(Guardian.requires(config, "HIGH", "vietcombank-xacthuc.top"), true);
});

test("Ed25519 không khả dụng trong trình duyệt: chính sách ký bị bỏ, mặc định nghiêm nhất", async () => {
  const { env, keys } = await setup();
  const signed = await keys.sign({ version: 2, require_levels: ["WARN"] });
  await env.local.set({ [POLICY_KEY]: signed });
  const original = crypto.subtle.importKey.bind(crypto.subtle);
  /** @type {any} */ (crypto.subtle).importKey = async (/** @type {any} */ format, /** @type {any} */ key, /** @type {any} */ algo, /** @type {any} */ ...rest) => {
    if (algo?.name === "Ed25519") throw new DOMException("không hỗ trợ", "NotSupportedError");
    return /** @type {any} */ (original)(format, key, algo, ...rest);
  };
  try {
    const config = await env.guardian.config();
    assert.equal(config.policy.source, "managed-only");
    assert.equal(config.mode, "ok");
  } finally {
    /** @type {any} */ (crypto.subtle).importKey = original;
  }
});
