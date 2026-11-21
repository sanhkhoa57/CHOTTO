// @ts-check
/**
 * Chế độ người giám hộ (Guardian mode): xin phép bằng mã thử thách–mã mở khóa, hoàn toàn offline.
 *
 * Gốc tin cậy (xem docs/GUARDIAN-MODE.md):
 * - Cờ bật, khóa công khai Ed25519, bí mật HMAC, ``min_policy_version`` CHỈ đọc từ ``chrome.storage.managed``
 *   (nguồn: registry HKLM, chỉ Admin ghi). Không bao giờ tin ``storage.local`` cho các giá trị này.
 * - Chính sách mở rộng (``storage.local``) chỉ được nhận nếu chữ ký Ed25519 đúng theo khóa trong managed và
 *   ``version >= min_policy_version``. Thiếu/sai/hỏng/thấp phiên bản: FAIL-CLOSED về mặc định nghiêm nhất
 *   (HIGH và BLOCKED đều cần mã), Guardian vẫn bật.
 *
 * Mọi phụ thuộc (kho lưu trữ, đồng hồ, số ngẫu nhiên, managed) được tiêm vào để kiểm thử bằng Node, không cần trình duyệt.
 * @module guardian/guardian
 */

import {
  CODE_DIGITS, computeCode, constantTimeEqual, formatNonce, fromBase64Url, newNonce, normalizeDomain, sha256Hex,
  verifyPolicySignature,
} from "./codec.js";

export const STATE_KEY = "guardianState";
export const POLICY_KEY = "guardianPolicy";
export const BOOT_KEY = "guardianBoot";

export const MAX_ATTEMPTS = 5;
export const LOCK_STEPS_MS = Object.freeze([30_000, 120_000, 600_000]);
export const DEFAULT_TTL_MS = 10 * 60_000;
export const CLOCK_TOLERANCE_MS = 5 * 60_000;
export const FAIL_DECAY_MS = 60 * 60_000;
const MAX_PENDING = 20;
const MAX_WARNINGS = 20;
const LEVELS = ["WARN", "HIGH", "BLOCKED"];
const STRICT_LEVELS = Object.freeze(["HIGH", "BLOCKED"]);

/**
 * @typedef {object} Policy Chính sách đang áp dụng.
 * @property {number} version 0 = mặc định nghiêm nhất (không có chính sách ký hợp lệ).
 * @property {Set<string>} requireLevels
 * @property {string[]} allowDomains
 * @property {number} ttlMs
 * @property {"managed-only" | "signed"} source
 */

/**
 * @typedef {object} GuardianConfig
 * @property {"off" | "ok" | "misconfigured"} mode
 * @property {Uint8Array | null} secret
 * @property {Uint8Array | null} publicKey
 * @property {number} minPolicyVersion
 * @property {Policy} policy
 * @property {string | null} policyProblem Lý do chính sách ký bị bỏ (``null`` nếu hợp lệ hoặc chưa có).
 */

/**
 * @typedef {object} Challenge
 * @property {string} nonce
 * @property {string} domain
 * @property {string} urlHash
 * @property {number} createdAt
 * @property {number} expiresAt
 * @property {number} attempts
 */

/**
 * @typedef {object} GState
 * @property {number} v
 * @property {string} bootId
 * @property {number} lastSeen
 * @property {number} fails Số lần nhập sai liên tiếp trên toàn tiện ích (về 0 khi mở khóa thành công hoặc sau 1 giờ yên).
 * @property {number} lastFailAt
 * @property {number} lockedUntil
 * @property {Record<string, Challenge>} challenges
 * @property {{ts: number, msg: string}[]} warnings
 */

/** @returns {Policy} Mặc định nghiêm nhất. */
export function strictPolicy() {
  return { version: 0, requireLevels: new Set(STRICT_LEVELS), allowDomains: [], ttlMs: DEFAULT_TTL_MS, source: "managed-only" };
}

/**
 * Kiểm tra cấu trúc payload chính sách (chuỗi JSON đã được xác minh chữ ký).
 * @param {unknown} data
 * @returns {Policy}
 * @throws {TypeError} Sai cấu trúc.
 */
export function parsePolicyPayload(data) {
  const p = /** @type {Record<string, any>} */ (data);
  if (!p || typeof p !== "object" || Array.isArray(p)) throw new TypeError("policy không phải đối tượng");
  if (!Number.isInteger(p.version) || p.version < 1) throw new TypeError("version không hợp lệ");
  const levels = p.require_levels ?? [...STRICT_LEVELS];
  if (!Array.isArray(levels) || levels.length === 0 || !levels.every((l) => LEVELS.includes(l))) {
    throw new TypeError("require_levels không hợp lệ");
  }
  const allow = p.allow_domains ?? [];
  if (!Array.isArray(allow) || allow.length > 500) throw new TypeError("allow_domains không hợp lệ");
  const domains = allow.map((d) => {
    const n = typeof d === "string" ? normalizeDomain(d) : null;
    if (n === null) throw new TypeError("allow_domains chứa tên miền không hợp lệ");
    return n;
  });
  const ttlSec = p.challenge_ttl_sec ?? DEFAULT_TTL_MS / 1000;
  if (!Number.isInteger(ttlSec) || ttlSec < 60 || ttlSec > 3600) throw new TypeError("challenge_ttl_sec ngoài 60..3600");
  // BLOCKED (danh sách đen) luôn cần mã, chính sách không thể nới ra.
  return { version: p.version, requireLevels: new Set([...levels, "BLOCKED"]), allowDomains: domains, ttlMs: ttlSec * 1000, source: "signed" };
}

/**
 * @param {unknown} value
 * @returns {boolean}
 */
function truthy(value) {
  return value === true || value === 1 || value === "1" || value === "true";
}

/**
 * @param {Uint8Array} bytes
 * @returns {string}
 */
function toHex(bytes) {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Đọc cấu hình Guardian: managed (tin cậy) + chính sách ký (qua kênh không đặc quyền, phải xác minh).
 * Không bao giờ ném lỗi: mọi hỏng hóc dẫn tới mặc định nghiêm nhất, trừ khi managed nói Guardian TẮT.
 * @param {Record<string, unknown> | null} managed Nội dung ``storage.managed`` (``null`` = không đọc được).
 * @param {unknown} envelope Giá trị lưu ở ``storage.local[POLICY_KEY]``.
 * @returns {Promise<GuardianConfig>}
 */
export async function resolveConfig(managed, envelope) {
  if (!managed || !truthy(managed.guardian_enabled)) {
    return { mode: "off", secret: null, publicKey: null, minPolicyVersion: 0, policy: strictPolicy(), policyProblem: null };
  }
  /** @type {Uint8Array | null} */
  let secret = null;
  /** @type {Uint8Array | null} */
  let publicKey = null;
  try {
    secret = fromBase64Url(String(managed.guardian_secret ?? ""));
    if (secret.length < 16) secret = null;
  } catch {
    secret = null;
  }
  try {
    publicKey = fromBase64Url(String(managed.guardian_public_key ?? ""));
    if (publicKey.length !== 32) publicKey = null;
  } catch {
    publicKey = null;
  }
  const rawMin = managed.min_policy_version;
  const minPolicyVersion = Number.isInteger(rawMin) && /** @type {number} */ (rawMin) >= 0 ? /** @type {number} */ (rawMin) : 0;
  const mode = secret === null ? "misconfigured" : "ok";

  let policy = strictPolicy();
  /** @type {string | null} */
  let policyProblem = null;
  if (envelope !== undefined && envelope !== null) {
    try {
      policy = await verifyEnvelope(envelope, publicKey, minPolicyVersion);
    } catch (error) {
      policy = strictPolicy();
      policyProblem = error instanceof Error ? error.message : String(error);
    }
  }
  return { mode, secret, publicKey, minPolicyVersion, policy, policyProblem };
}

/**
 * Xác minh phong bì ``{payload, signature}``.
 * @param {unknown} envelope
 * @param {Uint8Array | null} publicKey
 * @param {number} minPolicyVersion
 * @returns {Promise<Policy>}
 * @throws {Error} Thiếu khóa, sai chữ ký, sai cấu trúc hoặc version thấp hơn mức tối thiểu.
 */
export async function verifyEnvelope(envelope, publicKey, minPolicyVersion) {
  const e = /** @type {Record<string, unknown>} */ (envelope);
  if (!e || typeof e !== "object" || typeof e.payload !== "string" || typeof e.signature !== "string") {
    throw new Error("chính sách hỏng (thiếu payload/signature)");
  }
  if (publicKey === null) throw new Error("managed storage thiếu khóa công khai hợp lệ");
  let signature;
  try {
    signature = fromBase64Url(e.signature);
  } catch {
    throw new Error("chữ ký không phải base64");
  }
  if (!(await verifyPolicySignature(publicKey, e.payload, signature))) throw new Error("chữ ký không hợp lệ");
  let parsed;
  try {
    parsed = JSON.parse(e.payload);
  } catch {
    throw new Error("payload không phải JSON");
  }
  const policy = parsePolicyPayload(parsed);
  if (policy.version < minPolicyVersion) {
    throw new Error(`phiên bản ${policy.version} thấp hơn mức tối thiểu ${minPolicyVersion} (chống hạ cấp)`);
  }
  return policy;
}

/**
 * @typedef {object} GuardianDeps
 * @property {() => Promise<Record<string, unknown> | null>} readManaged
 * @property {{get: (key: string) => Promise<any>, set: (items: Record<string, unknown>) => Promise<void>}} local
 * @property {{get: (key: string) => Promise<any>, set: (items: Record<string, unknown>) => Promise<void>}} session
 * @property {() => number} now
 * @property {(n: number) => Uint8Array} [random]
 */

export class Guardian {
  /** @param {GuardianDeps} deps */
  constructor(deps) {
    this.deps = deps;
    /** @type {Promise<unknown>} */
    this.queue = Promise.resolve();
    /** @type {Record<string, unknown> | null} */
    this.lastManaged = null;
  }

  /**
   * Chạy tuần tự (tránh mất cập nhật khi nhiều thông điệp đến cùng lúc).
   * @template T
   * @param {() => Promise<T>} task
   * @returns {Promise<T>}
   */
  serial(task) {
    const run = this.queue.then(task, task);
    this.queue = run.catch(() => undefined);
    return run;
  }

  /** @returns {Promise<GuardianConfig>} */
  async config() {
    /** @type {Record<string, unknown> | null} */
    let managed = null;
    try {
      managed = await this.deps.readManaged();
      this.lastManaged = managed;
    } catch {
      managed = this.lastManaged; // không đọc được managed (ví dụ không có schema): dùng bản đọc tốt gần nhất; chưa từng có thì coi như tắt
    }
    let envelope;
    try {
      envelope = (await this.deps.local.get(POLICY_KEY))?.[POLICY_KEY];
    } catch {
      envelope = { corrupt: true };
    }
    return resolveConfig(managed, envelope);
  }

  /**
   * @param {number} n
   * @returns {Uint8Array}
   */
  randomBytes(n) {
    return (this.deps.random ?? ((k) => crypto.getRandomValues(new Uint8Array(k))))(n);
  }

  /**
   * Nạp trạng thái, áp các quy tắc thời gian/khởi động lại. Gọi trong ``serial``.
   * @returns {Promise<GState>}
   */
  async loadState() {
    const now = this.deps.now();
    const fresh = () => /** @type {GState} */ ({
      v: 1, bootId: "", lastSeen: now, fails: 0, lastFailAt: 0, lockedUntil: 0, challenges: {}, warnings: [],
    });
    /** @type {GState} */
    let state;
    try {
      const stored = (await this.deps.local.get(STATE_KEY))?.[STATE_KEY];
      state = stored && typeof stored === "object" && stored.v === 1 ? { ...fresh(), ...stored } : fresh();
      if (typeof state.challenges !== "object" || state.challenges === null) state.challenges = {};
      if (!Array.isArray(state.warnings)) state.warnings = [];
    } catch {
      state = fresh();
    }
    // 1) Trình duyệt khởi động lại (storage.session mất) → không chắc về thời gian → hủy mọi thử thách.
    let boot = "";
    try {
      boot = String((await this.deps.session.get(BOOT_KEY))?.[BOOT_KEY] ?? "");
    } catch {
      boot = "";
    }
    if (boot === "" || boot !== state.bootId) {
      state.challenges = {};
      state.bootId = boot || toHex(this.randomBytes(8));
      try {
        await this.deps.session.set({ [BOOT_KEY]: state.bootId });
      } catch {
        /* không ghi được: lần sau sẽ lại hủy, vẫn an toàn */
      }
    }
    // 2) Lùi giờ hệ thống quá 5 phút → hủy mọi thử thách và ghi cảnh báo.
    if (now < state.lastSeen - CLOCK_TOLERANCE_MS) {
      state.challenges = {};
      this.warn(state, now, `Giờ hệ thống bị lùi ${Math.round((state.lastSeen - now) / 1000)} giây: đã hủy mọi thử thách đang chờ.`);
      state.lastSeen = now;
    } else {
      state.lastSeen = Math.max(state.lastSeen, now);
    }
    // 3) Dọn thử thách hết hạn; bộ đếm sai tự nguội sau 1 giờ yên.
    for (const [id, ch] of Object.entries(state.challenges)) if (now >= ch.expiresAt) delete state.challenges[id];
    if (state.fails > 0 && now - Math.max(state.lastFailAt, state.lockedUntil) > FAIL_DECAY_MS) state.fails = 0;
    return state;
  }

  /**
   * @param {GState} state
   * @param {number} ts
   * @param {string} msg
   */
  warn(state, ts, msg) {
    state.warnings = [...state.warnings, { ts, msg }].slice(-MAX_WARNINGS);
  }

  /** @param {GState} state */
  async saveState(state) {
    await this.deps.local.set({ [STATE_KEY]: state });
  }

  /**
   * Link ở mức ``level`` và tên miền ``domain`` có cần xin phép người giám hộ không?
   * (Danh sách "luôn cho phép" không bao giờ áp cho BLOCKED.)
   * @param {GuardianConfig} config
   * @param {string} level
   * @param {string} domain
   * @returns {boolean}
   */
  static requires(config, level, domain) {
    if (config.mode === "off") return false;
    if (!config.policy.requireLevels.has(level)) return false;
    if (level !== "BLOCKED" && config.policy.allowDomains.includes(domain)) return false;
    return true;
  }

  /**
   * Phát một thử thách mới cho ``url``.
   * @param {{url: string, domain: string}} request
   * @returns {Promise<{status: "challenge", id: string, nonce: string, nonceText: string, domain: string, expiresAt: number, attemptsLeft: number}
   *   | {status: "locked", until: number} | {status: "misconfigured"}>}
   */
  issue({ url, domain }) {
    return this.serial(async () => {
      const config = await this.config();
      const state = await this.loadState();
      const now = this.deps.now();
      const normalized = normalizeDomain(domain);
      if (config.mode !== "ok" || normalized === null) {
        await this.saveState(state);
        return { status: /** @type {const} */ ("misconfigured") };
      }
      if (now < state.lockedUntil) {
        await this.saveState(state);
        return { status: /** @type {const} */ ("locked"), until: state.lockedUntil };
      }
      const urlHash = await sha256Hex(url);
      for (const [id, ch] of Object.entries(state.challenges)) if (ch.urlHash === urlHash) delete state.challenges[id];
      const pending = Object.entries(state.challenges).sort((a, b) => a[1].createdAt - b[1].createdAt);
      while (pending.length >= MAX_PENDING) {
        const oldest = pending.shift();
        if (oldest) delete state.challenges[oldest[0]];
      }
      const id = toHex(this.randomBytes(16));
      const nonce = newNonce((n) => this.randomBytes(n));
      state.challenges[id] = { nonce, domain: normalized, urlHash, createdAt: now, expiresAt: now + config.policy.ttlMs, attempts: 0 };
      await this.saveState(state);
      return {
        status: "challenge", id, nonce, nonceText: formatNonce(nonce), domain: normalized,
        expiresAt: now + config.policy.ttlMs, attemptsLeft: MAX_ATTEMPTS,
      };
    });
  }

  /**
   * Thử mã mở khóa. Đúng thì xóa thử thách NGAY (dùng một lần) và trả ``ok``; người gọi chỉ mở ĐÚNG ``url`` đó.
   * @param {{id: string, code: string, url: string}} attempt
   * @returns {Promise<{ok: true} | {ok: false, reason: "format" | "gone" | "locked" | "wrong" | "destroyed" | "misconfigured" | "mismatch",
   *   attemptsLeft?: number, lockedUntil?: number}>}
   */
  submit({ id, code, url }) {
    return this.serial(async () => {
      const config = await this.config();
      const state = await this.loadState();
      const now = this.deps.now();
      /**
       * @param {Record<string, unknown>} extra
       * @returns {Promise<any>}
       */
      const done = async (extra) => {
        await this.saveState(state);
        return extra;
      };
      if (config.mode !== "ok" || config.secret === null) return done({ ok: false, reason: "misconfigured" });
      const challenge = Object.prototype.hasOwnProperty.call(state.challenges, id) ? state.challenges[id] : undefined;
      if (!challenge) return done({ ok: false, reason: "gone" }); // chưa có, đã dùng, hết hạn, bị hủy (khởi động lại/lùi giờ/khóa)
      if (now < state.lockedUntil) return done({ ok: false, reason: "locked", lockedUntil: state.lockedUntil });
      const clean = String(code).replace(/\s/g, "");
      if (!new RegExp(`^\\d{${CODE_DIGITS}}$`).test(clean)) {
        return done({ ok: false, reason: "format", attemptsLeft: MAX_ATTEMPTS - challenge.attempts });
      }
      if (challenge.urlHash !== (await sha256Hex(url))) return done({ ok: false, reason: "mismatch" });
      const expected = await computeCode(config.secret, challenge.domain, challenge.nonce);
      if (constantTimeEqual(expected, clean)) {
        delete state.challenges[id];
        state.fails = 0;
        state.lockedUntil = 0;
        return done({ ok: true });
      }
      challenge.attempts += 1;
      state.fails += 1;
      state.lastFailAt = now;
      if (state.fails % MAX_ATTEMPTS === 0) {
        const step = Math.min(state.fails / MAX_ATTEMPTS, LOCK_STEPS_MS.length) - 1;
        state.lockedUntil = now + LOCK_STEPS_MS[step];
        state.challenges = {};
        this.warn(state, now, `Nhập sai ${state.fails} lần liên tiếp: khóa ${LOCK_STEPS_MS[step] / 1000} giây, đã hủy mọi thử thách.`);
        return done({ ok: false, reason: "destroyed", lockedUntil: state.lockedUntil, attemptsLeft: 0 });
      }
      if (challenge.attempts >= MAX_ATTEMPTS) {
        delete state.challenges[id];
        return done({ ok: false, reason: "destroyed", attemptsLeft: 0 });
      }
      return done({ ok: false, reason: "wrong", attemptsLeft: MAX_ATTEMPTS - challenge.attempts });
    });
  }

  /**
   * Trạng thái chỉ đọc cho trang cài đặt.
   * @returns {Promise<Record<string, unknown>>}
   */
  status() {
    return this.serial(async () => {
      const config = await this.config();
      const state = await this.loadState();
      await this.saveState(state);
      return {
        mode: config.mode,
        policySource: config.policy.source,
        policyVersion: config.policy.version,
        minPolicyVersion: config.minPolicyVersion,
        policyProblem: config.policyProblem,
        requireLevels: [...config.policy.requireLevels],
        allowDomains: config.policy.allowDomains,
        ttlSeconds: config.policy.ttlMs / 1000,
        lockedUntil: state.lockedUntil > this.deps.now() ? state.lockedUntil : 0,
        pending: Object.keys(state.challenges).length,
        warnings: state.warnings,
      };
    });
  }

  /**
   * Nhập chính sách đã ký (kênh không đặc quyền): chỉ lưu nếu xác minh đúng ngay lúc này.
   * @param {string} text JSON của phong bì ``{payload, signature}``.
   * @returns {Promise<{ok: boolean, error?: string, version?: number}>}
   */
  importPolicy(text) {
    return this.serial(async () => {
      let envelope;
      try {
        envelope = JSON.parse(text);
      } catch {
        return { ok: false, error: "không phải JSON" };
      }
      const config = await this.config();
      if (config.mode === "off") return { ok: false, error: "Guardian chưa được bật bởi chính sách quản lý" };
      try {
        const policy = await verifyEnvelope(envelope, config.publicKey, config.minPolicyVersion);
        await this.deps.local.set({ [POLICY_KEY]: { payload: envelope.payload, signature: envelope.signature } });
        return { ok: true, version: policy.version };
      } catch (error) {
        return { ok: false, error: error instanceof Error ? error.message : String(error) };
      }
    });
  }
}
