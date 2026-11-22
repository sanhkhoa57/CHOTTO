// @ts-check
/**
 * E2E trang người giám hộ (guardian/index.html): trang tĩnh, không máy chủ riêng. Test phục vụ thư mục guardian/ bằng một máy chủ
 * HTTP cục bộ (localhost) và kiểm tra: cài đặt bí mật, mã tính đúng theo vector chung, cảnh báo HIGH/BLOCKED khớp engine Node,
 * không gọi mạng (CSP + theo dõi mọi yêu cầu), chạy offline sau lần tải đầu, xóa khỏi thiết bị, các đường lỗi.
 */
import assert from "node:assert/strict";
import { mkdir, readFile } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { after, afterEach, before, beforeEach, test } from "node:test";

import { chromium } from "playwright";

import { makeEngine, REPO_DIR } from "../tests/helpers.mjs";

const GUARDIAN_DIR = path.join(REPO_DIR, "guardian");
const SHOTS = path.join(REPO_DIR, "docs", "guardian", "ux", "after");
const vectors = JSON.parse(await readFile(path.join(REPO_DIR, "tests", "data", "guardian_vectors.json"), "utf-8"));
const SETUP = `CHOTTO-GUARDIAN-SETUP-v1:${vectors.hmac_secret}`;
const NONCE = "K7QF3MZDX9HP";

/** @type {http.Server} */
let server;
/** @type {string} */
let base;
/** @type {import("playwright").Browser} */
let browser;
/** @type {import("playwright").BrowserContext} */
let context;
/** @type {string[]} */
const requests = [];

before(async () => {
  await mkdir(SHOTS, { recursive: true });
  server = http.createServer(async (req, res) => {
    const name = new URL(req.url ?? "/", "http://x").pathname.replace(/^\/guardian\//, "");
    const file = name === "" || name === "index.html" ? "index.html" : name === "sw.js" ? "sw.js" : null;
    if (file === null) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { "content-type": file.endsWith(".js") ? "text/javascript" : "text/html; charset=utf-8" });
    res.end(await readFile(path.join(GUARDIAN_DIR, file)));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(undefined)));
  base = `http://localhost:${/** @type {import("node:net").AddressInfo} */ (server.address()).port}/guardian/`;
  browser = await chromium.launch({ channel: "chromium", headless: true, executablePath: process.env.CHROMIUM_PATH || undefined });
});

/** Mỗi test một ngữ cảnh mới (localStorage sạch, không dính trạng thái của test trước). */
beforeEach(async () => {
  context = await browser.newContext({ viewport: { width: 420, height: 900 }, locale: "vi-VN" });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: new URL(base).origin });
  context.on("request", (request) => requests.push(request.url()));
});

afterEach(async () => {
  await context?.close();
});

after(async () => {
  await browser?.close();
  await new Promise((resolve) => server?.close(() => resolve(undefined)));
});

/** @param {string} domain @param {string} [nonce] */
const link = (domain, nonce = NONCE) => `${base}#v=1&d=${encodeURIComponent(domain)}&n=${nonce}`;

/** @param {import("playwright").Page} page */
async function install(page) {
  await page.goto(base);
  await page.fill("#setup-input", SETUP);
  await page.click("text=Lưu vào thiết bị này");
  await page.waitForSelector("text=Đã lưu vào thiết bị này.");
}

/**
 * Mở màn hình duyệt và đợi chấm xong.
 * @param {import("playwright").Page} page
 * @param {string} domain
 * @param {string} [nonce]
 */
async function review(page, domain, nonce = NONCE) {
  await page.goto("about:blank");
  await page.goto(link(domain, nonce));
  await page.waitForSelector(".verdict");
}

/** @param {import("playwright").Page} page */
async function allow(page) {
  await page.getByRole("button", { name: "Cho mở", exact: true }).click();
  const confirm = page.locator(".confirm");
  if (await confirm.isVisible()) await page.getByRole("button", { name: "Rồi, vẫn cho mở", exact: true }).click();
  await page.waitForSelector(".code");
  return (await page.textContent(".code")) ?? "";
}

/** @param {string} code "123456" */
const spaced = (code) => `${code.slice(0, 3)} ${code.slice(3)}`;

test("cài đặt một lần: dán chuỗi cài đặt, lưu trong localStorage; không có bí mật thì không tính mã", async () => {
  const page = await context.newPage();
  await page.goto(link("vietcombank-xacthuc.top"));
  await page.waitForSelector("text=Cài đặt một lần");
  assert.equal(await page.locator("button:has-text('Cho mở')").count(), 0, "chưa cài đặt thì chưa có nút cho mở");
  assert.match(await page.textContent("#app") ?? "", /Sau khi cài đặt xong, hãy mở lại liên kết/);
  await page.fill("#setup-input", "linh tinh");
  await page.click("text=Lưu vào thiết bị này");
  await page.waitForSelector("text=Chuỗi cài đặt chưa đúng");
  await page.screenshot({ path: path.join(SHOTS, "trang-nguoi-giam-ho-cai-dat.png") });
  await page.fill("#setup-input", SETUP);
  await page.click("text=Lưu vào thiết bị này");
  await page.waitForSelector("text=Đã lưu vào thiết bị này.");
  assert.equal(await page.evaluate(() => localStorage.getItem("chotto-guardian-secret-v1")), vectors.hmac_secret);
  await page.evaluate(() => localStorage.clear());
  await page.close();
});

test("liên kết cài đặt (#setup=…): chỉ lưu khi bấm; sau khi lưu thanh địa chỉ không còn bí mật", async () => {
  const page = await context.newPage();
  await page.goto(`${base}#setup=${vectors.hmac_secret}`);
  await page.waitForSelector("text=Cài đặt một lần");
  assert.equal(await page.evaluate(() => localStorage.getItem("chotto-guardian-secret-v1")), null, "chưa bấm Lưu thì chưa lưu");
  assert.equal(await page.inputValue("#setup-input"), vectors.hmac_secret);
  await page.click("text=Lưu vào thiết bị này");
  await page.waitForSelector("text=Đã lưu vào thiết bị này.");
  assert.ok(!page.url().includes(vectors.hmac_secret), "bí mật không còn trong địa chỉ");
  assert.equal(await page.evaluate(() => localStorage.getItem("chotto-guardian-secret-v1")), vectors.hmac_secret);
  await page.evaluate(() => localStorage.clear());
  await page.close();
});

test("mã tính đúng theo vector chung Python ↔ JS cho mọi ca; mức rủi ro khớp engine Node; HIGH/BLOCKED có cảnh báo đỏ", async () => {
  const { engine } = await makeEngine();
  const page = await context.newPage();
  await install(page);
  for (const v of vectors.codes) {
    await review(page, v.domain, v.nonce);
    const level = await page.getAttribute(".verdict", "data-level");
    const expected = (await engine.inspect(`https://${v.domain}/`)).level;
    assert.equal(level, expected, `mức của ${v.domain} phải khớp engine`);
    const danger = level === "HIGH" || level === "BLOCKED";
    assert.equal(await page.locator(".banner").count() > 0 && /lừa đảo/.test(await page.locator(".banner").first().textContent() ?? ""), danger, v.domain);
    assert.equal(await allow(page), spaced(v.code), `mã của ${v.domain}`);
    assert.match(await page.textContent(".reply") ?? "", new RegExp(`^Mã của bạn là ${spaced(v.code)}$`));
  }
  await page.evaluate(() => localStorage.clear());
  await page.close();
});

test("màn hình duyệt: tên trang web to rõ, địa chỉ trang đang chạy, cảnh báo đỏ, hai nút; Không cho mở soạn sẵn câu trả lời và chép vào clipboard", async () => {
  const page = await context.newPage();
  await install(page);
  await review(page, "vietcombank-xacthuc.top");
  assert.equal((await page.textContent(".site"))?.trim(), "vietcombank-xacthuc.top");
  assert.match(await page.textContent(".addr") ?? "", new RegExp(`Bạn đang ở trang: .*localhost:\\d+/guardian/`), "luôn hiện địa chỉ trang đang chạy");
  assert.equal((await page.textContent(".banner"))?.trim(), "Đây có thể là lừa đảo. Chỉ cho mở nếu bạn chắc chắn.");
  assert.deepEqual(await page.locator("#decision > button").allTextContents(), ["Không cho mở", "Cho mở"]);
  assert.ok((await page.locator("h1").evaluate((el) => parseFloat(getComputedStyle(el).fontSize))) >= 24, "tiêu đề >= 24px");
  assert.ok((await page.locator("body").evaluate((el) => parseFloat(getComputedStyle(el).fontSize))) >= 18, "chữ thân >= 18px");
  for (const handle of await page.locator("button").elementHandles()) {
    if (!(await handle.isVisible())) continue;
    const box = await handle.boundingBox();
    assert.ok(box && box.height >= 48 && box.width >= 48, `vùng bấm >= 48px: ${await handle.textContent()}`);
  }
  await page.screenshot({ path: path.join(SHOTS, "trang-nguoi-giam-ho-duyet.png"), fullPage: true });

  await page.getByRole("button", { name: "Không cho mở", exact: true }).click();
  await page.waitForSelector(".reply");
  assert.equal(await page.textContent(".reply"), "Đừng mở link này nhé.");
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), "Đừng mở link này nhé.");
  assert.equal(await page.locator(".code").count(), 0, "từ chối thì không có mã");
  await page.screenshot({ path: path.join(SHOTS, "trang-nguoi-giam-ho-khong-cho-mo.png"), fullPage: true });

  // "Cho mở" với link nguy hiểm: hỏi lại một lần ("đã gọi lại chưa?"); mã chỉ hiện sau khi xác nhận.
  await review(page, "vietcombank-xacthuc.top");
  await page.getByRole("button", { name: "Cho mở", exact: true }).click();
  assert.ok(await page.locator(".confirm").isVisible());
  assert.equal(await page.locator(".code").count(), 0, "chưa xác nhận thì chưa có mã");
  await page.getByRole("button", { name: "Chưa, quay lại", exact: true }).click();
  assert.ok(!(await page.locator(".confirm").isVisible()));
  const code = await allow(page);
  assert.match(code, /^\d{3} \d{3}$/);
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), `Mã của bạn là ${code}`);
  await page.getByRole("button", { name: "Chép mã", exact: true }).click();
  await page.waitForSelector("text=Đã chép.");
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), code);
  assert.ok(((await page.locator(".code").evaluate((el) => parseFloat(getComputedStyle(el).fontSize)))) >= 44, "mã rất lớn");
  await page.screenshot({ path: path.join(SHOTS, "trang-nguoi-giam-ho-cho-mo.png"), fullPage: true });

  // Link an toàn: không có cảnh báo đỏ và không hỏi lại.
  await review(page, "vietcombank.com.vn");
  assert.equal(await page.locator(".banner").count(), 0);
  await page.getByRole("button", { name: "Cho mở", exact: true }).click();
  await page.waitForSelector(".code");
  await page.emulateMedia({ colorScheme: "dark" });
  await review(page, "vietcombank-xacthuc.top");
  await page.screenshot({ path: path.join(SHOTS, "trang-nguoi-giam-ho-duyet-toi.png"), fullPage: true });
  await page.emulateMedia({ colorScheme: "light" });
  await page.evaluate(() => localStorage.clear());
  await page.close();
});

test("không gọi mạng: CSP chặn connect-src, mọi yêu cầu chỉ tới chính nơi host trang, trang không chứa API mạng", async () => {
  const html = await readFile(path.join(GUARDIAN_DIR, "index.html"), "utf-8");
  const csp = /http-equiv="Content-Security-Policy" content="([^"]+)"/.exec(html)?.[1] ?? "";
  assert.match(csp, /default-src 'none'/);
  assert.match(csp, /connect-src 'none'/);
  assert.doesNotMatch(csp, /unsafe-inline|unsafe-eval|https?:|\*/);
  const page = await context.newPage();
  await install(page);
  await review(page, "momo-hoantien.vip");
  await allow(page);
  const violations = await page.evaluate(() => new Promise((resolve) => {
    /** @type {string[]} */
    const seen = [];
    document.addEventListener("securitypolicyviolation", (e) => seen.push(e.violatedDirective));
    fetch("https://example.com/leak?x=1").then(() => resolve(["fetch đã chạy"]), () => setTimeout(() => resolve(seen), 50));
  }));
  assert.ok(/** @type {string[]} */ (violations).some((d) => d.startsWith("connect-src")), "fetch ra ngoài bị CSP chặn");
  const origin = new URL(base).origin;
  const outside = requests.filter((u) => !u.startsWith(origin) && !u.startsWith("about:") && !u.startsWith("data:"));
  assert.deepEqual(outside, [], "không có yêu cầu nào ra ngoài nơi host trang");
  assert.ok(requests.every((u) => !u.includes("#") && !u.includes("K7QF3MZDX9HP")), "fragment không bao giờ nằm trong yêu cầu");
  const script = /<script>([\s\S]*)<\/script>/.exec(html)?.[1] ?? "";
  assert.ok(script.length > 100_000, "đã nhúng engine và dữ liệu");
  for (const banned of ["fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "EventSource", "importScripts", "indexedDB"]) {
    assert.ok(!script.includes(banned), `trang không được dùng ${banned}`);
  }
  await page.evaluate(() => localStorage.clear());
  await page.close();
});

test("chạy offline sau lần tải đầu (service worker giữ một bản của trang)", async () => {
  const page = await context.newPage();
  await install(page);
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => undefined));
  await page.reload();
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  await context.setOffline(true);
  try {
    await page.goto(link("vietcombank-xacthuc.top"));
    await page.waitForSelector(".verdict");
    assert.equal((await page.textContent(".site"))?.trim(), "vietcombank-xacthuc.top");
    assert.match(await allow(page), /^\d{3} \d{3}$/);
  } finally {
    await context.setOffline(false);
  }
  await page.evaluate(() => localStorage.clear());
  await page.close();
});

test("xóa khỏi thiết bị này (hai bước) và các đường lỗi: sai phiên bản, liên kết hỏng, nhập tay mã đọc qua điện thoại", async () => {
  const page = await context.newPage();
  await install(page);
  await page.goto("about:blank");
  await page.goto(`${base}#v=2&d=a.com&n=${NONCE}`);
  await page.waitForSelector("text=do bản khác tạo ra");
  await page.goto("about:blank");
  await page.goto(`${base}#v=1&d=a.com&n=HONG`);
  await page.waitForSelector("text=không đọc được");

  // Nhập tay: tên trang web (kể cả dạng "abc[.]com" trong lời nhắn) + mã 12 ký tự đọc qua điện thoại.
  await page.goto("about:blank");
  await page.goto(base);
  await page.waitForSelector("text=Chưa có lời nhắn nào");
  await page.click("summary:has-text('Người nhờ đọc mã qua điện thoại?')");
  await page.fill("#manual-site", "vietcombank-xacthuc[.]top");
  await page.fill("#manual-code", "k7qf 3mzd x9h1");
  await page.click("text=Xem trang này");
  await page.waitForSelector("text=Mã gồm 12 ký tự");
  await page.fill("#manual-code", "k7qf-3mzd-x9hp");
  await page.click("text=Xem trang này");
  await page.waitForSelector(".verdict");
  const manualCode = await allow(page);
  const expected = vectors.codes.find((/** @type {any} */ c) => c.domain === "vietcombank-xacthuc.top" && c.nonce === NONCE).code;
  assert.equal(manualCode, spaced(expected));

  await page.goto("about:blank");
  await page.goto(base);
  await page.click("summary:has-text('Cài đặt trên thiết bị này')");
  await page.getByRole("button", { name: "Xóa khỏi thiết bị này", exact: true }).click();
  assert.equal(await page.evaluate(() => localStorage.getItem("chotto-guardian-secret-v1")) !== null, true, "mới hỏi, chưa xóa");
  await page.getByRole("button", { name: "Hủy", exact: true }).click();
  assert.equal(await page.evaluate(() => localStorage.getItem("chotto-guardian-secret-v1")) !== null, true);
  await page.getByRole("button", { name: "Xóa khỏi thiết bị này", exact: true }).click();
  await page.getByRole("button", { name: "Xóa", exact: true }).click();
  await page.waitForSelector("text=Cài đặt một lần");
  assert.equal(await page.evaluate(() => localStorage.getItem("chotto-guardian-secret-v1")), null);
  await page.close();
});

test("mở trực tiếp từ đĩa (file://) cũng chạy được", async () => {
  const page = await context.newPage();
  const url = new URL(`file:///${GUARDIAN_DIR.replaceAll("\\", "/")}/index.html`);
  await page.goto(`${url.href}#v=1&d=vietcombank-xacthuc.top&n=${NONCE}`);
  await page.waitForSelector("text=Cài đặt một lần");
  await page.fill("#setup-input", SETUP);
  await page.click("text=Lưu vào thiết bị này");
  await page.waitForSelector("text=Đã lưu vào thiết bị này.");
  await page.goto("about:blank");
  await page.goto(`${url.href}#v=1&d=vietcombank-xacthuc.top&n=${NONCE}`);
  await page.waitForSelector(".verdict");
  assert.match(await allow(page), /^\d{3} \d{3}$/);
  await page.evaluate(() => localStorage.clear());
  await page.close();
});

