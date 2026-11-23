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
import http from "node:http";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { parseShareFragment } from "../src/guardian/share.js";

const EXTENSION_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_DIR = path.resolve(EXTENSION_DIR, "..", "..");
const SHOTS = path.join(REPO_DIR, "docs", "guardian", "ux", "after");
const SETTINGS_SHOT = path.join(REPO_DIR, "docs", "guardian", "04-settings.png");
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

/** Máy chủ tĩnh cục bộ phục vụ trang người giám hộ (guardian/index.html), như khi host ở GitHub Pages. */
/** @type {http.Server} */
let pageServer;
/** @type {string} */
let pageBase = "";

const GUARDIAN_ON = {
  guardian_enabled: true, guardian_public_key: vectors.policy.public_key, guardian_secret: vectors.hmac_secret, min_policy_version: 0,
  /** @type {string | undefined} */
  guardian_page_url: undefined,
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
  pageServer = http.createServer(async (req, res) => {
    const name = new URL(req.url ?? "/", "http://x").pathname.replace(/^\/guardian\//, "");
    const file = name === "" || name === "index.html" ? "index.html" : name === "sw.js" ? "sw.js" : null;
    if (file === null) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { "content-type": file.endsWith(".js") ? "text/javascript" : "text/html; charset=utf-8" });
    res.end(await readFile(path.join(REPO_DIR, "guardian", file)));
  });
  await new Promise((resolve) => pageServer.listen(0, "127.0.0.1", () => resolve(undefined)));
  pageBase = `http://localhost:${/** @type {import("node:net").AddressInfo} */ (pageServer.address()).port}/guardian/`;
  GUARDIAN_ON.guardian_page_url = pageBase;
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
  // Đọc được clipboard để kiểm tra lời nhắn được tự chép.
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: "https://chat.zalo.me" });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: new URL(pageBase).origin });
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.protocol === "chrome-extension:" || url.hostname === "localhost") return route.continue();
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
  await new Promise((resolve) => pageServer?.close(() => resolve(undefined)));
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
    const text = (node) => (node.nodeType === 3 ? node.nodeValue : node.nodeName === "STYLE" ? "" : [...(node.children ?? []), ...(node.shadowRoots ?? [])].map(text).join(""));
    /** @param {any} node */
    const center = async (node) => {
      await live.send("DOM.scrollIntoViewIfNeeded", { backendNodeId: node.backendNodeId }).catch(() => undefined);
      const { model } = await live.send("DOM.getBoxModel", { backendNodeId: node.backendNodeId });
      const [x1, y1, , , x3, y3] = model.content;
      return { x: (x1 + x3) / 2, y: (y1 + y3) / 2 };
    };
    /** @param {string} cls */
    const allByClass = (cls) => inside.filter((n) => (attr(n, "class") ?? "").split(" ").includes(cls));
    /** Phần tử có đang hiện không (tính cả ``hidden`` và CSS ẩn của bước 2). @param {any} node */
    const visible = async (node) => {
      const { object } = await live.send("DOM.resolveNode", { backendNodeId: node.backendNodeId });
      const { result } = await live.send("Runtime.callFunctionOn", {
        objectId: object.objectId, functionDeclaration: "function(){ return this.checkVisibility(); }", returnByValue: true,
      });
      return result.value === true;
    };
    /** Phần tử đầu tiên có lớp ``cls`` ĐANG HIỆN. @param {string} cls */
    const firstVisible = async (cls) => {
      for (const node of allByClass(cls)) if (await visible(node)) return node;
      return undefined;
    };
    /** Mọi nút đang hiện: tên lớp đầu tiên + chữ. */
    const visibleButtons = async () => {
      const out = [];
      for (const node of inside.filter((n) => n.nodeName === "BUTTON")) {
        if (await visible(node)) out.push({ cls: (attr(node, "class") ?? "").split(" ")[0], text: text(node).trim() });
      }
      return out;
    };
    return { all: inside, attr, byClass, allByClass, firstVisible, text, center, visible, visibleButtons, host, hostText: text(host) };
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
 * Bấm "Nhờ người giám hộ xem giúp": một chạm; lời nhắn được TỰ chép vào clipboard. Đọc lời nhắn từ clipboard.
 * @param {import("playwright").Page} page
 */
async function askGuardian(page) {
  const s = await shield(page);
  const at = await s.center(s.byClass("sh-proceed"));
  await page.mouse.click(at.x, at.y);
  const opened = await shieldWith(page, /Đã chép lời nhắn\./);
  const message = (await page.evaluate(() => navigator.clipboard.readText())).replaceAll("\r\n", "\n");   // Windows đổi xuống dòng thành CRLF
  const lines = message.split("\n");
  assert.equal(lines.length, 3, `lời nhắn gồm 3 dòng:\n${message}`);
  const link = lines[2];
  const parsed = parseShareFragment(new URL(link).hash);
  assert.ok(parsed.ok, `liên kết phải có #fragment đúng định dạng: ${link}`);
  if (!parsed.ok) throw new Error("fragment sai");
  await page.waitForTimeout(250);   // đợi ô nhập nhận focus
  return { opened, message, link, domain: parsed.domain, nonce: parsed.nonce };
}

/**
 * @param {import("playwright").Page} page
 * @param {string} code
 */
async function enterCode(page, code) {
  await page.keyboard.press("Control+A");   // thay nội dung cũ (nếu có) trong ô nhập
  await page.keyboard.type(code);
  await page.keyboard.press("Enter");
}

/**
 * Chụp ảnh sau khi hoạt ảnh xuất hiện/chuyển màu đã xong.
 * @param {import("playwright").Page} page
 * @param {string} name
 */
async function shot(page, name) {
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(SHOTS, name) });
}

/** @param {string} code 123456 → "123 456" */
const spaced = (code) => `${code.slice(0, 3)} ${code.slice(3)}`;

test("màn hình 1 (chặn): một câu kết luận, tên trang web, CHỈ HAI nút chính; các lựa chọn khác thu gọn trong 'Thêm lựa chọn'", async () => {
  const page = await context.newPage();
  await openZalo(page);
  await page.click("#phish");
  const s = await shield(page);
  assert.match(s.hostText, /Link này có thể là lừa đảo\. Đừng mở\./);
  assert.match(s.hostText, /vietcombank/);
  assert.match(s.hostText, /Nhờ người giám hộ xem giúp/);
  assert.doesNotMatch(s.hostText, /Vẫn mở|Xin phép/);
  assert.equal(s.byClass("sh-ring"), undefined, "không còn vòng đếm ngược");
  assert.equal(s.attr(s.byClass("sh-proceed"), "aria-disabled"), "false");
  // Chỉ hai nút chính đang hiện (Đóng, Nhờ…) + liên kết nhỏ "Thêm lựa chọn".
  assert.deepEqual(await s.visibleButtons(), [
    { cls: "sh-back", text: "Đóng" },
    { cls: "sh-proceed", text: "Nhờ người giám hộ xem giúp" },
    { cls: "gd-more-toggle", text: "Thêm lựa chọn" },
  ]);
  assert.equal(s.attr(s.byClass("gd-more-toggle"), "aria-expanded"), "false");
  assert.ok(!(await s.visible(s.byClass("sh-more"))), "Sao chép/Báo cho người gửi đang thu gọn");
  await shot(page, "man-hinh-1-chan.png");
  await page.emulateMedia({ colorScheme: "dark" });
  await page.waitForTimeout(400);
  await shot(page, "man-hinh-1-chan-toi.png");
  await page.emulateMedia({ colorScheme: "light" });

  // "Thêm lựa chọn": mở ra thì thấy Sao chép địa chỉ, Báo cho người gửi, Xem vì sao.
  await page.mouse.click((await s.center(s.byClass("gd-more-toggle"))).x, (await s.center(s.byClass("gd-more-toggle"))).y);
  const more = await shield(page);
  assert.equal(more.attr(more.byClass("gd-more-toggle"), "aria-expanded"), "true");
  assert.ok(await more.visible(more.byClass("sh-more")));
  assert.match(more.hostText, /Sao chép địa chỉ/);
  assert.match(more.hostText, /Báo cho người gửi/);
  assert.match(more.hostText, /Xem vì sao/);
  await shot(page, "man-hinh-1-them-lua-chon.png");

  // Lỗi trạng thái cũ: bấm "Báo cho người gửi" (hiện "Đã chép lời nhắn, hãy dán vào Zalo") rồi sang bước xin phép:
  // dòng đó phải biến mất, không lẫn vào màn hình 2.
  const report = more.allByClass("sh-ghost").find((n) => /Báo cho người gửi/.test(more.text(n)));
  assert.ok(report);
  await page.mouse.click((await more.center(report)).x, (await more.center(report)).y);
  const reported = await shieldWith(page, /hãy dán vào Zalo/);
  assert.match(reported.text(reported.byClass("sh-note")), /Đã chép lời nhắn, hãy dán vào Zalo/);
  const after = await askGuardian(page);
  assert.equal(after.opened.text(after.opened.byClass("sh-note")), "", "dòng trạng thái của bước trước đã bị xóa");
  assert.ok(!(await after.opened.visible(after.opened.byClass("sh-note"))));
  await page.keyboard.press("Escape");
  await page.close();
});

test("màn hình 2 (đã nhờ): lời nhắn tự chép vào clipboard, một ô nhập số; mã đúng của công cụ Python mở đúng link", async () => {
  const page = await context.newPage();
  await openZalo(page);
  await page.click("#phish");
  const { opened, message, link, domain, nonce } = await askGuardian(page);

  // Lời nhắn: câu ngắn + tên trang web (không bấm được) + liên kết trang người giám hộ với dữ liệu ở #fragment.
  assert.equal(domain, "vietcombank-xacthuc.top");
  assert.match(message, /^Mình nhận được link này, nhờ xem giúp có mở được không\?\nTrang web: vietcombank-xacthuc\[\.\]top\nhttps?:\/\//);
  assert.equal(new URL(link).search, "", "dữ liệu không nằm trong query");
  assert.match(new URL(link).hash, /^#v=1&d=vietcombank-xacthuc\.top&n=[2-9A-HJKMNP-Z]{12}$/);

  // Màn hình 2 chỉ có: hướng dẫn một dòng, nút Chép lại, MỘT ô nhập, nút Mở link, phương án dự phòng thu gọn, Đóng.
  assert.match(opened.hostText, /Đã chép lời nhắn\./);
  assert.match(opened.hostText, /Mở Zalo, dán vào cuộc trò chuyện với người giám hộ rồi gửi\./);
  assert.match(opened.hostText, /Chép lại/);
  const inputs = opened.all.filter((n) => n.nodeName === "INPUT");
  assert.equal(inputs.length, 1, "một ô nhập số duy nhất");
  assert.equal(opened.attr(inputs[0], "inputmode"), "numeric");
  assert.equal(opened.attr(inputs[0], "autocomplete"), "one-time-code");
  assert.deepEqual((await opened.visibleButtons()).map((b) => b.cls), ["gd-ghost", "gd-open", "gd-more-toggle", "gd-close"]);
  for (const banned of ["tên miền", "thử thách", "nonce", "QR", "HMAC", "chính sách"]) {
    assert.ok(!opened.hostText.includes(banned), `không dùng từ kỹ thuật "${banned}"`);
  }
  for (const banned of [" con ", "bố mẹ", " cháu "]) assert.ok(!opened.hostText.toLowerCase().includes(banned), `không xưng "${banned}"`);
  assert.match(opened.hostText, /người giám hộ/);
  assert.doesNotMatch(opened.hostText, /hết hạn sau|\d:\d\d/, "không có đồng hồ đếm ngược ở màn hình chính");
  await shot(page, "man-hinh-2-da-nho.png");
  await page.emulateMedia({ colorScheme: "dark" });
  await page.waitForTimeout(400);
  await shot(page, "man-hinh-2-da-nho-toi.png");
  await page.emulateMedia({ colorScheme: "light" });

  // Phương án dự phòng: mã đọc bằng miệng (nhóm 4 ký tự, không I/L/O/0/1) và hình vuông quét.
  const s = await shield(page);
  const fbToggle = await s.firstVisible("gd-more-toggle");
  assert.ok(fbToggle);
  await page.mouse.click((await s.center(fbToggle)).x, (await s.center(fbToggle)).y);
  const fb = await shield(page);
  const spoken = fb.text(fb.byClass("gd-nonce"));
  assert.equal(spoken.replaceAll("-", ""), nonce);
  assert.match(spoken, /^([2-9A-HJKMNP-Z]{4}-){2}[2-9A-HJKMNP-Z]{4}$/);
  assert.ok(fb.all.some((n) => n.nodeName === "svg" && fb.attr(n, "role") === "img"), "có hình vuông quét");
  await shot(page, "man-hinh-2-du-phong.png");
  const fbToggle2 = await fb.firstVisible("gd-more-toggle");
  assert.ok(fbToggle2);
  await page.mouse.click((await fb.center(fbToggle2)).x, (await fb.center(fbToggle2)).y);
  const box = await shield(page);
  await page.mouse.click((await box.center(box.byClass("gd-code"))).x, (await box.center(box.byClass("gd-code"))).y);   // bấm vào ô nhập rồi gõ

  // Nhập sai: báo bằng câu đời thường + số lần còn lại, KHÔNG mở gì.
  const code = codeFromPython(domain, nonce);
  const bad = code === "000000" ? "111111" : "000000";
  await enterCode(page, bad);
  assert.ok(await shieldWith(page, /Mã chưa đúng\. Còn 4 lần thử\./));
  await shot(page, "man-hinh-2-sai-ma.png");
  assert.equal(await navigationsTo("https://vietcombank-xacthuc.top"), 0);

  // Nhập thiếu số: nhắc nhẹ, không tốn lượt.
  await enterCode(page, "12 34");
  assert.ok(await shieldWith(page, /Mã gồm đúng 6 số/));

  // Mã đúng viết kiểu "123 456" → mở đúng link, đóng hộp thoại.
  const opening = context.waitForEvent("page");
  await enterCode(page, spaced(code));
  const tab = await opening;
  await waitFor(async () => ((await navigationsTo("https://vietcombank-xacthuc.top/login")) === 1 ? true : null));
  await waitFor(async () => ((await shieldDom(page)) === null ? true : null));
  await tab.close();

  // Dùng lại đúng mã đó cho lời nhắn mới của cùng link: bị từ chối (mã mới, lời nhắn cũ đã xóa).
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
  const blocked = await askGuardian(page);   // (nonce đọc từ lời nhắn trong clipboard)
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
  await shot(page, "man-hinh-2-khoa.png");
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

test("LUỒNG ĐẦY ĐỦ: bấm link nguy hiểm → Nhờ người giám hộ → clipboard → mở liên kết ở trang người giám hộ → Cho mở → mã → nhập → link mở", async () => {
  const zalo = await context.newPage();
  await openZalo(zalo);
  await zalo.click("#phish");
  const openedBefore = await navigationsTo("https://vietcombank-xacthuc.top/login");
  const { message, link } = await askGuardian(zalo);
  assert.ok(link.startsWith(pageBase), "liên kết trỏ tới trang người giám hộ đã cấu hình trong managed");

  // Điện thoại của người giám hộ: cài đặt một lần bằng liên kết cài đặt (bí mật thử), rồi mở liên kết nhận được qua Zalo.
  const phone = await context.newPage();
  await phone.setViewportSize({ width: 420, height: 900 });
  await phone.goto(`${pageBase}#setup=${vectors.hmac_secret}`);
  await phone.getByRole("button", { name: "Lưu vào thiết bị này", exact: true }).click();
  await phone.waitForSelector("text=Đã lưu vào thiết bị này.");
  await phone.goto("about:blank");
  await phone.goto(message.split("\n")[2]);
  await phone.waitForSelector(".verdict");
  assert.equal((await phone.textContent(".site"))?.trim(), "vietcombank-xacthuc.top");
  assert.match(await phone.textContent(".banner") ?? "", /Đây có thể là lừa đảo/);
  await phone.getByRole("button", { name: "Cho mở", exact: true }).click();
  await phone.getByRole("button", { name: "Rồi, vẫn cho mở", exact: true }).click();
  await phone.waitForSelector(".code");
  const reply = await phone.textContent(".reply");
  assert.match(reply ?? "", /^Mã của bạn là \d{3} \d{3}$/);
  assert.equal(await phone.evaluate(() => navigator.clipboard.readText()), reply);
  const code = (await phone.textContent(".code"))?.replace(/\s/g, "") ?? "";
  await phone.close();

  // Người được bảo vệ nhận câu trả lời, dán/gõ vào ô duy nhất (cả dạng "123 456") → link mở.
  assert.equal(await navigationsTo("https://vietcombank-xacthuc.top/login"), openedBefore, "chưa nhập mã thì chưa mở");
  await zalo.bringToFront();
  const opening = context.waitForEvent("page");
  const s = await shield(zalo);
  await zalo.mouse.click((await s.center(s.byClass("gd-code"))).x, (await s.center(s.byClass("gd-code"))).y);
  await enterCode(zalo, spaced(code));
  const tab = await opening;
  await waitFor(async () => ((await navigationsTo("https://vietcombank-xacthuc.top/login")) === openedBefore + 1 ? true : null));
  await waitFor(async () => ((await shieldDom(zalo)) === null ? true : null));
  await tab.close();
  await zalo.close();
});

test("luồng 'Không cho mở': người giám hộ từ chối, câu trả lời soạn sẵn; link không mở; mã của người giám hộ cho trang khác không dùng được", async () => {
  const zalo = await context.newPage();
  await openZalo(zalo);
  await zalo.click("#phish");
  const openedBefore = await navigationsTo("https://vietcombank-xacthuc.top/login");
  const { message } = await askGuardian(zalo);
  const phone = await context.newPage();
  await phone.goto(`${pageBase}#setup=${vectors.hmac_secret}`);
  await phone.getByRole("button", { name: "Lưu vào thiết bị này", exact: true }).click();
  await phone.waitForSelector("text=Đã lưu vào thiết bị này.");
  await phone.goto("about:blank");
  await phone.goto(message.split("\n")[2]);
  await phone.waitForSelector(".verdict");
  await phone.getByRole("button", { name: "Không cho mở", exact: true }).click();
  await phone.waitForSelector(".reply");
  assert.equal(await phone.textContent(".reply"), "Đừng mở link này nhé.");
  assert.equal(await phone.locator(".code").count(), 0, "không có mã khi từ chối");
  assert.equal(await phone.evaluate(() => navigator.clipboard.readText()), "Đừng mở link này nhé.");

  // Kẻ gian gửi người giám hộ liên kết khác (trang khác): mã tính cho trang đó KHÔNG mở được link đang bị chặn ở đây.
  await phone.goto("about:blank");
  await phone.goto(`${pageBase}#v=1&d=vcb-digibank-xacthuc.top&n=${message.split("\n")[2].split("&n=")[1]}`);
  await phone.waitForSelector(".verdict");
  await phone.getByRole("button", { name: "Cho mở", exact: true }).click();
  await phone.getByRole("button", { name: "Rồi, vẫn cho mở", exact: true }).click();
  await phone.waitForSelector(".code");
  const otherCode = (await phone.textContent(".code"))?.replace(/\s/g, "") ?? "";
  await phone.close();

  await zalo.bringToFront();
  const s = await shield(zalo);
  await zalo.mouse.click((await s.center(s.byClass("gd-code"))).x, (await s.center(s.byClass("gd-code"))).y);
  await enterCode(zalo, otherCode);
  assert.ok(await shieldWith(zalo, /Mã chưa đúng\. Còn \d lần thử\./));
  assert.equal(await navigationsTo("https://vietcombank-xacthuc.top/login"), openedBefore, "người giám hộ không cho mở thì link không mở");
  await zalo.keyboard.press("Escape");
  await waitFor(async () => ((await shieldDom(zalo)) === null ? true : null));
  await zalo.close();
});

test("guardian_name: 'Nhờ Mai xem giúp' (tên in đậm); không có tên thì 'người giám hộ'; tên độc hại được lọc và gán bằng textContent", async () => {
  await setManaged({ ...GUARDIAN_ON, guardian_name: "  Mai‮  " });
  try {
    const page = await context.newPage();
    await openZalo(page);
    await page.click("#phish");
    const s = await shield(page);
    assert.deepEqual((await s.visibleButtons()).map((b) => b.text), ["Đóng", "Nhờ Mai xem giúp", "Thêm lựa chọn"]);
    const bold = await s.firstVisible("gd-name");
    assert.ok(bold, "tên người giám hộ in đậm trên nút");
    assert.equal(s.text(bold), "Mai", "tên đã lọc ký tự đảo chiều/khoảng trắng thừa");
    await shot(page, "man-hinh-1-co-ten.png");
    const { opened } = await askGuardian(page);
    assert.match(opened.hostText, /Gửi lời nhắn cho Mai/);
    await page.keyboard.press("Escape");
    await page.close();

    // Tên có thẻ HTML/script: hiện nguyên chữ, không tạo phần tử nào.
    await setManaged({ ...GUARDIAN_ON, guardian_name: "<img src=x onerror=alert(1)><b>Lan</b>" });
    const evil = await context.newPage();
    await openZalo(evil);
    await evil.click("#phish");
    const e = await shield(evil);
    assert.equal(e.all.filter((n) => n.nodeName === "IMG").length, 0, "không có thẻ IMG");
    assert.ok(e.hostText.includes("Nhờ <img src=x onerror=alert(1)>"), "tên hiện nguyên văn như chữ (cắt ở 30 ký tự)");
    await evil.keyboard.press("Escape");
    await evil.close();

    // Không có tên (hoặc chỉ toàn ký tự điều khiển): dùng "người giám hộ".
    await setManaged({ ...GUARDIAN_ON, guardian_name: "\u0000​" });
    const plain = await context.newPage();
    await openZalo(plain);
    await plain.click("#phish");
    const p = await shield(plain);
    assert.deepEqual((await p.visibleButtons()).map((b) => b.text), ["Đóng", "Nhờ người giám hộ xem giúp", "Thêm lựa chọn"]);
    assert.equal(await p.firstVisible("gd-name"), undefined, "không có tên thì không có phần in đậm");
    await plain.keyboard.press("Escape");
    await plain.close();
  } finally {
    await setManaged(GUARDIAN_ON);
  }
});

test("mức WARN giữ hành vi cũ (đếm ngược rồi cho mở); link an toàn mở thẳng", async () => {
  const page = await context.newPage();
  await openZalo(page);
  await page.click("#warn");
  const s = await shield(page);
  assert.match(s.hostText, /Vẫn mở/);
  assert.doesNotMatch(s.hostText, /Nhờ người giám hộ/);
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
    assert.doesNotMatch(s.hostText, /Nhờ người giám hộ/);
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
    await page.goto(`chrome-extension://${extensionId}/src/ui/options.html#settings`);
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
    await page.locator("#guardian").screenshot({ path: SETTINGS_SHOT });

    // Chính sách ký (chỉ HIGH + BLOCKED, cho phép vietcombank.com.vn) đang có hiệu lực; hạ min xuống rồi thay bằng bản thấp hơn thì bị bỏ.
    await worker.evaluate(async () => { await chrome.storage.local.remove("guardianPolicy"); });
    await page.close();
  } finally {
    await setManaged(GUARDIAN_ON);
  }
});
