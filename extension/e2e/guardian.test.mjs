// @ts-check
/**
 * E2E Guardian mode: nạp tiện ích vào Chromium thật, MÔ PHỎNG ``chrome.storage.managed`` (không ghi registry; trong test
 * thay ``chrome.storage.managed.get`` của service worker), bấm link nguy hiểm trên trang Zalo giả, nhận thử thách, tính mã
 * bằng công cụ Python thật (``tools/guardian.py code``), nhập mã, kiểm tra link chỉ mở khi mã đúng. Chụp ảnh vào docs/guardian/.
 *
 * Chạy: ``npm run e2e`` (cần Chromium của Playwright; đặt ``PYTHON`` nếu lệnh ``python`` không có trong PATH).
 */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const EXTENSION_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_DIR = path.resolve(EXTENSION_DIR, "..");
const SHOTS = path.join(REPO_DIR, "docs", "guardian");
const PAGE = await readFile(path.join(EXTENSION_DIR, "e2e", "guardian_zalo.html"), "utf-8");
const vectors = JSON.parse(await readFile(path.join(REPO_DIR, "tests", "data", "guardian_vectors.json"), "utf-8"));
const PYTHON = process.env.PYTHON || "python";

/** @type {import("playwright").BrowserContext} */
let context;
/** @type {import("playwright").Worker} */
let worker;
/** @type {string} */
let profileDir;
/** @type {string} */
let guardianDir;
/** @type {string} */
let extensionId;
/** @type {Record<string, unknown>} */
let managed = {};

const GUARDIAN_ON = {
  guardian_enabled: true, guardian_public_key: vectors.policy.public_key, guardian_secret: vectors.hmac_secret, min_policy_version: 0,
};

/**
 * Đặt nội dung "managed storage" giả trong service worker (nhớ lại để áp lại nếu service worker khởi động lại).
 * @param {Record<string, unknown>} value
 */
async function setManaged(value) {
  managed = value;
  await applyManaged(worker);
}

/** @param {import("playwright").Worker} target */
async function applyManaged(target) {
  await target.evaluate((value) => {
    /** @type {any} */ (chrome.storage.managed).get = async () => structuredClone(value);
  }, managed);
}

/**
 * Mã mở khóa do công cụ Python THẬT của người giám hộ tính (``tools/guardian.py code``).
 * @param {string} domain
 * @param {string} nonce
 * @returns {string} 6 chữ số
 */
function codeFromPython(domain, nonce) {
  const out = execFileSync(PYTHON, [path.join(REPO_DIR, "tools", "guardian.py"), "--dir", guardianDir, "code", domain, nonce, "--yes"], {
    cwd: REPO_DIR, encoding: "utf-8", env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  });
  const match = out.match(/(\d{3}) (\d{3})\s*\n/);
  assert.ok(match, `không đọc được mã từ công cụ Python:\n${out}`);
  return `${match[1]}${match[2]}`;
}

before(async () => {
  profileDir = await mkdtemp(path.join(os.tmpdir(), "chotto-guardian-e2e-"));
  guardianDir = await mkdtemp(path.join(os.tmpdir(), "chotto-guardian-keys-"));
  await writeFile(path.join(guardianDir, "keys.json"), JSON.stringify({
    ed25519_private: "", ed25519_public: vectors.policy.public_key, hmac_secret: vectors.hmac_secret, policy_version: 0,
  }));
  await mkdir(SHOTS, { recursive: true });
  context = await chromium.launchPersistentContext(profileDir, {
    channel: "chromium",
    headless: true,
    viewport: { width: 1100, height: 900 },
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: [`--disable-extensions-except=${EXTENSION_DIR}`, `--load-extension=${EXTENSION_DIR}`],
  });
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.protocol === "chrome-extension:") return route.continue();
    if (url.host === "chat.zalo.me") return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: PAGE });
    return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: `<!doctype html><title>DEST</title><p>${url.host}</p>` });
  });
  [worker] = context.serviceWorkers();
  if (!worker) worker = await context.waitForEvent("serviceworker");
  extensionId = new URL(worker.url()).host;
  await waitFor(() => worker.evaluate(() => (typeof chrome !== "undefined" && chrome.webNavigation && chrome.storage ? true : null)));
  context.on("serviceworker", (w) => { waitFor(() => w.evaluate(() => (typeof chrome !== "undefined" && chrome.storage ? true : null))).then(() => applyManaged(w)).catch(() => undefined); });
  await worker.evaluate(() => {
    const scope = /** @type {any} */ (globalThis);
    scope.__navs = [];
    chrome.webNavigation.onBeforeNavigate.addListener((d) => { if (d.frameId === 0) scope.__navs.push(d.url); });
  });
  await setManaged(GUARDIAN_ON);
  // Lần cài đầu tiên tiện ích tự mở trang cài đặt: dùng chính trang đó (tránh đua điều hướng).
  const options = await waitFor(async () => context.pages().find((p) => p.url().includes("/src/ui/options.html")) ?? null, 15000);
  await options.waitForLoadState("load");
  await options.evaluate(() => chrome.runtime.sendMessage({
    type: "settings", changes: { tier3Enabled: false, autoUpdate: false, frictionSeconds: 3 },
  }));
  await options.close();
});

after(async () => {
  await context?.close();
  if (profileDir) await rm(profileDir, { recursive: true, force: true });
  if (guardianDir) await rm(guardianDir, { recursive: true, force: true });
});

/**
 * @template T
 * @param {() => Promise<T | null | undefined>} probe
 * @param {number} [timeoutMs]
 * @returns {Promise<T>}
 */
async function waitFor(probe, timeoutMs = 8000) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const value = await probe();
    if (value !== null && value !== undefined) return value;
    if (Date.now() > deadline) throw new Error("Hết thời gian chờ");
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

/** @param {string} prefix */
async function navigationsTo(prefix) {
  const navs = await worker.evaluate(() => /** @type {any} */ (globalThis).__navs ?? []);
  return navs.filter((/** @type {string} */ u) => u.startsWith(prefix)).length;
}

/** @type {WeakMap<import("playwright").Page, import("playwright").CDPSession>} */
const sessions = new WeakMap();

/**
 * Mọi nút bên trong hộp thoại CHOTTO (xuyên Shadow DOM đóng) qua CDP.
 * @param {import("playwright").Page} page
 */
async function shieldDom(page) {
  let session = sessions.get(page);
  if (!session) {
    session = await context.newCDPSession(page);
    sessions.set(page, session);
  }
  const live = session;
  try {
    const { root } = await live.send("DOM.getDocument", { depth: -1, pierce: true });
    /** @type {any[]} */
    const all = [];
    /** @param {any} node */
    const walk = (node) => {
      all.push(node);
      for (const child of [...(node.children ?? []), ...(node.shadowRoots ?? [])]) walk(child);
      if (node.contentDocument) walk(node.contentDocument);
    };
    walk(root);
    const host = all.find((n) => n.nodeName === "CHOTTO-SHIELD" && JSON.stringify(n).includes('"DIALOG"'));
    if (!host) return null;
    /** @type {any[]} */
    const inside = [];
    /** @param {any} node */
    const walkIn = (node) => {
      inside.push(node);
      for (const child of [...(node.children ?? []), ...(node.shadowRoots ?? [])]) walkIn(child);
    };
    walkIn(host);
    /** @param {any} node @param {string} name */
    const attr = (node, name) => {
      const list = node.attributes ?? [];
      for (let i = 0; i < list.length; i += 2) if (list[i] === name) return list[i + 1];
      return undefined;
    };
    /** @param {string} cls */
    const byClass = (cls) => inside.find((n) => (attr(n, "class") ?? "").split(" ").includes(cls));
    /**
     * @param {any} node
     * @returns {string}
     */
    const text = (node) => (node.nodeType === 3 ? node.nodeValue : [...(node.children ?? []), ...(node.shadowRoots ?? [])].map(text).join(""));
    /** @param {any} node */
    const center = async (node) => {
      await live.send("DOM.scrollIntoViewIfNeeded", { backendNodeId: node.backendNodeId }).catch(() => undefined);
      const { model } = await live.send("DOM.getBoxModel", { backendNodeId: node.backendNodeId });
      const [x1, y1, , , x3, y3] = model.content;
      return { x: (x1 + x3) / 2, y: (y1 + y3) / 2 };
    };
    return { all: inside, attr, byClass, text, center, host, hostText: text(host) };
  } catch (error) {
    if (/box model|No node|detached|closed/i.test(String(error))) return null;
    throw error;
  }
}

/** @param {import("playwright").Page} page */
const shield = (page) => waitFor(() => shieldDom(page));

/**
 * Đợi đến khi hộp thoại có chữ khớp ``pattern``.
 * @param {import("playwright").Page} page
 * @param {RegExp} pattern
 */
const shieldWith = (page, pattern) => waitFor(async () => {
  const s = await shieldDom(page);
  return s && pattern.test(s.hostText) ? s : null;
});

/** @param {import("playwright").Page} page */
async function openZalo(page) {
  await page.goto("https://chat.zalo.me/");
}

/**
 * Bấm "Xin phép người giám hộ" và đọc thử thách.
 * @param {import("playwright").Page} page
 */
async function askGuardian(page) {
  const s = await shield(page);
  const ask = s.byClass("sh-proceed");
  const at = await s.center(ask);
  await page.mouse.click(at.x, at.y);
  const opened = await shieldWith(page, /Mã thử thách/);
  const domain = opened.text(opened.byClass("gd-domain"));
  const nonceText = opened.text(opened.byClass("gd-nonce"));
  return { opened, domain, nonce: nonceText.replace("-", ""), nonceText };
}

/**
 * @param {import("playwright").Page} page
 * @param {string} code
 */
async function enterCode(page, code) {
  await page.keyboard.type(code);
  await page.keyboard.press("Enter");
}

test("Guardian bật: link HIGH đổi nút thành 'Xin phép người giám hộ', hiện thử thách + QR; mã đúng của công cụ Python mở đúng link", async () => {
  const page = await context.newPage();
  await openZalo(page);
  await page.click("#phish");
  const s = await shield(page);
  assert.match(s.hostText, /Xin phép người giám hộ/);
  assert.doesNotMatch(s.hostText, /Vẫn mở/);
  assert.equal(s.byClass("sh-ring"), undefined, "không còn vòng đếm ngược");
  assert.equal(s.attr(s.byClass("sh-proceed"), "aria-disabled"), "false");
  assert.equal(s.attr(s.byClass("sh-proceed"), "aria-expanded"), "false");

  const { opened, domain, nonce, nonceText } = await askGuardian(page);
  assert.equal(domain, "vietcombank-xacthuc.top");
  assert.match(nonceText, /^[A-Z2-7]{4}-[A-Z2-7]{4}$/);
  assert.match(opened.hostText, /Chỉ người giám hộ của bạn mới đưa mã này\. Ai gọi điện xin mã thử thách là kẻ lừa đảo\./);
  assert.ok(opened.all.some((n) => n.nodeName === "svg" && opened.attr(n, "role") === "img"), "có mã QR");
  assert.equal(opened.all.filter((n) => n.nodeName === "INPUT").length, 6, "6 ô nhập");
  assert.match(opened.hostText, /hết hạn sau (10:00|9:5\d)/);
  await page.screenshot({ path: path.join(SHOTS, "01-challenge.png") });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SHOTS, "05-challenge-dark.png") });
  await page.emulateMedia({ colorScheme: "light" });

  // Nhập sai: báo rõ, đếm lượt còn lại, KHÔNG mở gì.
  const code = codeFromPython(domain, nonce);
  const bad = code === "000000" ? "111111" : "000000";
  await enterCode(page, bad);
  const wrong = await shieldWith(page, /Mã chưa đúng\. Còn 4 lần thử\./);
  assert.ok(wrong);
  await page.screenshot({ path: path.join(SHOTS, "02-wrong-code.png") });
  assert.equal(await navigationsTo("https://vietcombank-xacthuc.top"), 0);

  // Mã đúng (dán một lần vào ô đầu: tự phân phối 6 chữ số) → mở đúng link, đóng hộp thoại.
  const opening = context.waitForEvent("page");
  await page.keyboard.type(code);
  await page.keyboard.press("Enter");
  const tab = await opening;
  await waitFor(async () => ((await navigationsTo("https://vietcombank-xacthuc.top/login")) === 1 ? true : null));
  await waitFor(async () => ((await shieldDom(page)) === null ? true : null));
  await tab.close();

  // Dùng lại đúng mã đó cho một thử thách mới của cùng link: bị từ chối (nonce mới, thử thách cũ đã xóa).
  await page.click("#phish");
  const again = await askGuardian(page);
  assert.notEqual(again.nonce, nonce);
  await enterCode(page, code);
  assert.ok(await shieldWith(page, /Mã chưa đúng\. Còn 4 lần thử\./));
  assert.equal(await navigationsTo("https://vietcombank-xacthuc.top/login"), 1);
  await page.keyboard.press("Escape");
  await page.close();
});

test("mã đúng của tên miền khác bị từ chối; quá 5 lần sai thì hủy thử thách và khóa tạm", async () => {
  // Bộ đếm sai là TOÀN CỤC (không reset khi đổi thử thách), nên bắt đầu từ trạng thái sạch để đếm đúng 5 lần.
  await worker.evaluate(async () => {
    const { guardianState } = /** @type {{guardianState: any}} */ (await chrome.storage.local.get("guardianState"));
    guardianState.fails = 0;
    await chrome.storage.local.set({ guardianState });
  });
  const page = await context.newPage();
  await openZalo(page);
  await page.click("#blocked");
  const blocked = await askGuardian(page);
  assert.equal(blocked.domain, "vcb-digibank-xacthuc.top");
  const wrongDomainCode = codeFromPython("vietcombank-xacthuc.top", blocked.nonce);
  const real = codeFromPython(blocked.domain, blocked.nonce);
  assert.notEqual(wrongDomainCode, real);
  await enterCode(page, wrongDomainCode);
  assert.ok(await shieldWith(page, /Mã chưa đúng\. Còn 4 lần thử\./));
  for (const left of [3, 2, 1]) {
    await enterCode(page, wrongDomainCode);
    assert.ok(await shieldWith(page, new RegExp(`Còn ${left} lần thử`)));
  }
  await enterCode(page, wrongDomainCode);
  const locked = await shieldWith(page, /Đã nhập sai quá nhiều lần\.\s*Thử lại sau 0:\d\d\./);
  assert.ok(locked);
  assert.equal(locked.all.filter((n) => n.nodeName === "INPUT").length, 0, "hết ô nhập khi bị khóa");
  const renew = locked.byClass("gd-open");
  assert.equal(locked.attr(renew, "disabled") !== undefined, true, "nút tạo thử thách mới bị khóa");
  await page.screenshot({ path: path.join(SHOTS, "03-locked.png") });
  assert.equal(await navigationsTo("https://vcb-digibank-xacthuc.top"), 0);
  await page.keyboard.press("Escape");
  await waitFor(async () => ((await shieldDom(page)) === null ? true : null));

  // Đang khóa: bấm lại link vẫn xin được màn hình nhưng KHÔNG có thử thách mới.
  await page.click("#blocked");
  await shield(page);
  const s = await shield(page);
  await page.mouse.click((await s.center(s.byClass("sh-proceed"))).x, (await s.center(s.byClass("sh-proceed"))).y);
  assert.ok(await shieldWith(page, /Đã nhập sai quá nhiều lần/));
  await page.keyboard.press("Escape");

  // Hết khóa (mô phỏng thời gian trôi bằng cách sửa mốc khóa trong kho): thử thách mới, mã đúng mở được.
  await worker.evaluate(async () => {
    const { guardianState } = /** @type {{guardianState: any}} */ (await chrome.storage.local.get("guardianState"));
    guardianState.lockedUntil = 0;
    await chrome.storage.local.set({ guardianState });
  });
  await page.click("#blocked");
  const fresh = await askGuardian(page);
  const opening = context.waitForEvent("page");
  await enterCode(page, codeFromPython(fresh.domain, fresh.nonce));
  const tab = await opening;
  await waitFor(async () => ((await navigationsTo("https://vcb-digibank-xacthuc.top/")) === 1 ? true : null));
  await tab.close();
  await page.close();
});

test("mức WARN giữ hành vi cũ (đếm ngược rồi cho mở); link an toàn mở thẳng", async () => {
  const page = await context.newPage();
  await openZalo(page);
  await page.click("#warn");
  const s = await shield(page);
  assert.match(s.hostText, /Vẫn mở/);
  assert.doesNotMatch(s.hostText, /Xin phép người giám hộ/);
  assert.equal(s.attr(s.byClass("sh-proceed"), "aria-disabled"), "true");
  await page.keyboard.press("Escape");
  await waitFor(async () => ((await shieldDom(page)) === null ? true : null));
  const opening = context.waitForEvent("page");
  await page.click("#safe");
  const tab = await opening;
  await waitFor(async () => ((await navigationsTo("https://vietcombank.com.vn/")) >= 1 ? true : null));
  await tab.close();
  await page.close();
});

test("managed storage thiếu (Guardian tắt): link HIGH giữ nguyên hành vi cũ", async () => {
  await setManaged({});
  try {
    const page = await context.newPage();
    await openZalo(page);
    await page.click("#phish");
    const s = await shield(page);
    assert.match(s.hostText, /Vẫn mở/);
    assert.doesNotMatch(s.hostText, /Xin phép người giám hộ/);
    assert.ok(s.byClass("sh-ring"));
    await page.keyboard.press("Escape");
    await page.close();
  } finally {
    await setManaged(GUARDIAN_ON);
  }
});

test("trang cài đặt hiện trạng thái Guardian chỉ đọc; nhận chính sách ký đúng, từ chối chính sách sai chữ ký", async () => {
  await setManaged({ ...GUARDIAN_ON, min_policy_version: 7 });
  try {
    const page = await context.newPage();
    await page.setViewportSize({ width: 900, height: 1000 });
    await page.goto(`chrome-extension://${extensionId}/src/ui/options.html`);
    await page.waitForFunction(() => /Đang bật bởi chính sách quản lý/.test(document.getElementById("guardian-state")?.textContent ?? ""));
    assert.match(await page.textContent("#guardian-details") ?? "", /Mặc định nghiêm nhất/);
    assert.match(await page.textContent("#guardian-details") ?? "", /Phiên bản tối thiểu \(managed\)7/);
    assert.equal(await page.locator("#guardian input[type=checkbox]").count(), 0, "không có công tắc nào để tắt Guardian");

    const envelope = { payload: vectors.policy.payload, signature: vectors.policy.signature };
    await page.fill("#guardian-policy", JSON.stringify({ ...envelope, payload: envelope.payload.replace('"version":7', '"version":8') }));
    await page.click("#guardian-import button");
    await page.waitForFunction(() => /Không nhận: chữ ký không hợp lệ/.test(document.getElementById("guardian-import-status")?.textContent ?? ""));
    await page.fill("#guardian-policy", JSON.stringify(envelope));
    await page.click("#guardian-import button");
    await page.waitForFunction(() => /Chính sách đã ký hợp lệ, phiên bản 7/.test(document.getElementById("guardian-details")?.textContent ?? ""));
    assert.match(await page.textContent("#guardian-details") ?? "", /vietcombank\.com\.vn/);
    await page.locator("#guardian").screenshot({ path: path.join(SHOTS, "04-settings.png") });

    // Chính sách ký (chỉ HIGH + BLOCKED, cho phép vietcombank.com.vn) đang có hiệu lực; hạ min xuống rồi thay bằng bản thấp hơn thì bị bỏ.
    await worker.evaluate(async () => { await chrome.storage.local.remove("guardianPolicy"); });
    await page.close();
  } finally {
    await setManaged(GUARDIAN_ON);
  }
});
