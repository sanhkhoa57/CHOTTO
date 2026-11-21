// @ts-check
/** Kiểm thử phần "một chạm" của Guardian: lời nhắn, liên kết #fragment, ô nhập mã, tên người giám hộ, địa chỉ trang. */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

import { computeCode, fromBase64Url, normalizeCodeInput } from "../src/guardian/codec.js";
import { Guardian, resolveConfig } from "../src/guardian/guardian.js";
import {
  DEFAULT_PAGE_URL, buildShareLink, buildShareMessage, defangDomain, parseShareFragment, sanitizeName, sanitizePageUrl,
} from "../src/guardian/share.js";
import { REPO_DIR } from "./helpers.mjs";

const vectors = JSON.parse(await readFile(path.join(REPO_DIR, "tests", "data", "guardian_vectors.json"), "utf-8"));
const BASE = { guardian_enabled: true, guardian_public_key: vectors.policy.public_key, guardian_secret: vectors.hmac_secret, min_policy_version: 0 };
const PAGE = "https://example.github.io/CHOTTO/guardian/";

// Giao diện (script thường, gắn globalThis.ChottoGuardianUI) nạp được trong Node vì chỉ chạm DOM khi mount.
const UI_PATH = "../src/ui/guardian-ui.js";   // script thường (không phải module): nạp bằng đường dẫn biến để tsc không đòi export
await import(UI_PATH);
const UI = /** @type {any} */ (globalThis).ChottoGuardianUI;

test("lời nhắn: liên kết có #fragment đúng định dạng, không có query; tên miền được viết an toàn; không xưng hô theo vai", () => {
  const link = buildShareLink(PAGE, "vietcombank-xacthuc.top", "K7QF3MZDX9HP");
  assert.equal(link, `${PAGE}#v=1&d=vietcombank-xacthuc.top&n=K7QF3MZDX9HP`);
  const url = new URL(link);
  assert.equal(url.search, "", "dữ liệu không nằm trong query (query bị gửi lên máy chủ host trang)");
  assert.equal(url.hash, "#v=1&d=vietcombank-xacthuc.top&n=K7QF3MZDX9HP");
  assert.deepEqual(parseShareFragment(url.hash), { ok: true, domain: "vietcombank-xacthuc.top", nonce: "K7QF3MZDX9HP" });

  const message = buildShareMessage({ domain: "vietcombank-xacthuc.top", link });
  const lines = message.split("\n");
  assert.equal(lines.length, 3);
  assert.equal(lines[0], "Mình nhận được link này, nhờ xem giúp có mở được không?");
  assert.equal(lines[1], "Trang web: vietcombank-xacthuc[.]top");
  assert.equal(lines[2], link);
  assert.ok(!lines[1].includes("vietcombank-xacthuc.top"), "tên trang web bị 'vô hiệu hóa' để Zalo không tự biến thành liên kết bấm được");
  assert.equal(defangDomain("a.b.com"), "a[.]b[.]com");
  for (const banned of ["con", "bố", "mẹ", "cháu"]) {
    assert.ok(!new RegExp(`(^|\\s)${banned}(\\s|$)`, "i").test(message), `lời nhắn không được xưng "${banned}"`);
  }
  const v6 = buildShareLink(PAGE, "[::1]:8080", "K7QF3MZDX9HP");
  assert.deepEqual(parseShareFragment(new URL(v6).hash), { ok: true, domain: "[::1]:8080", nonce: "K7QF3MZDX9HP" });
});

test("đọc fragment: sai phiên bản/thiếu/sai mã bị từ chối; chấp nhận chữ thường và gạch", () => {
  assert.deepEqual(parseShareFragment(""), { ok: false, reason: "empty" });
  assert.deepEqual(parseShareFragment("#v=2&d=a.com&n=K7QF3MZDX9HP"), { ok: false, reason: "version" });
  assert.deepEqual(parseShareFragment("#v=1&d=a|b.com&n=K7QF3MZDX9HP"), { ok: false, reason: "domain" });
  assert.deepEqual(parseShareFragment("#v=1&d=a.com&n=K7QF3MZD"), { ok: false, reason: "nonce" });
  assert.deepEqual(parseShareFragment("v=1&d=A.COM.&n=k7qf-3mzd-x9hp"), { ok: true, domain: "a.com", nonce: "K7QF3MZDX9HP" });
});

test("ô nhập mã: chấp nhận '123 456', '123-456', cả câu dán nguyên; từ chối thiếu/thừa số (codec và giao diện cùng quy tắc)", () => {
  for (const ok of ["123456", "123 456", "123-456", " 123  456 ", "Mã của bạn là 123 456", "123.456"]) {
    assert.equal(normalizeCodeInput(ok), "123456", ok);
    assert.equal(UI.normalizeCode(ok), "123456", ok);
  }
  for (const bad of ["", "12345", "1234567", "abc", "123 45", "12 34 56 78"]) {
    assert.equal(normalizeCodeInput(bad), null, bad);
    assert.equal(UI.normalizeCode(bad), null, bad);
  }
});

test("service worker nhận mã có khoảng trắng/gạch như mã đúng (cùng quy tắc với ô nhập)", async () => {
  const area = () => {
    /** @type {Record<string, any>} */
    const items = {};
    return {
      get: async (/** @type {string} */ key) => (key in items ? { [key]: structuredClone(items[key]) } : {}),
      set: async (/** @type {Record<string, unknown>} */ values) => { Object.assign(items, structuredClone(values)); },
    };
  };
  const guardian = new Guardian({ readManaged: async () => BASE, local: area(), session: area(), now: () => 1_700_000_000_000 });
  const secret = fromBase64Url(vectors.hmac_secret);
  for (const [sep, url, domain] of [[" ", "https://a.example/x", "a.example"], ["-", "https://b.example/y", "b.example"]]) {
    const issued = await guardian.issue({ url, domain });
    assert.equal(issued.status, "challenge");
    if (issued.status !== "challenge") return;
    const code = await computeCode(secret, issued.domain, issued.nonce);
    assert.deepEqual(await guardian.submit({ id: issued.id, code: `${code.slice(0, 3)}${sep}${code.slice(3)}`, url }), { ok: true });
  }
});

test("guardian_name: hiển thị khi hợp lệ, lọc ký tự điều khiển, tối đa 30 ký tự; không có tên thì null; chỉ đọc từ managed", async () => {
  assert.equal(sanitizeName("  Bà   Lan "), "Bà Lan");
  assert.equal(sanitizeName("Con‮evil​"), "Con evil");
  assert.equal(sanitizeName("Hà\u0000\u0007 Nội"), "Hà Nội");
  assert.equal(sanitizeName("\n\t "), null);
  assert.equal(sanitizeName(42), null);
  assert.equal(sanitizeName("x".repeat(100))?.length, 30);
  assert.equal(Array.from(sanitizeName("😀".repeat(40)) ?? "").length, 30, "tính theo ký tự Unicode, không cắt đôi cặp thay thế");
  assert.equal(sanitizeName("<img src=x onerror=alert(1)>"), "<img src=x onerror=alert(1)>".slice(0, 30), "không biến đổi HTML: giao diện gán bằng textContent");
  assert.equal((await resolveConfig({ ...BASE, guardian_name: "  Mai  " }, undefined)).name, "Mai");
  assert.equal((await resolveConfig(BASE, undefined)).name, null);
  assert.equal((await resolveConfig({ ...BASE, guardian_name: "\u0000" }, undefined)).name, null);
  assert.equal((await resolveConfig({ guardian_name: "Mai" }, undefined)).name, null, "Guardian tắt thì không có tên");
  // Giao diện lọc lại một lần nữa (phòng thủ nhiều lớp) bằng cùng quy tắc.
  for (const v of vectors.names) assert.equal(UI.cleanName(v.input), v.expected, JSON.stringify(v.input));
});

test("guardian_page_url: chỉ nhận https (hoặc localhost), không tài khoản; sai thì dùng trang mặc định", async () => {
  assert.equal(sanitizePageUrl("https://example.com/g/?x=1#f"), "https://example.com/g/");
  assert.equal(sanitizePageUrl("http://example.com/g/"), null);
  assert.equal(sanitizePageUrl("javascript:alert(1)"), null);
  assert.equal(sanitizePageUrl("https://u:p@example.com/"), null);
  assert.equal((await resolveConfig({ ...BASE, guardian_page_url: "https://khac.example/g/" }, undefined)).pageUrl, "https://khac.example/g/");
  assert.equal((await resolveConfig({ ...BASE, guardian_page_url: "http://khac.example/" }, undefined)).pageUrl, DEFAULT_PAGE_URL);
  assert.equal((await resolveConfig(BASE, undefined)).pageUrl, DEFAULT_PAGE_URL);
});
