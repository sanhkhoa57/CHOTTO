// @ts-check
/**
 * Lời nhắn và liên kết gửi cho người giám hộ (Guardian mode, trải nghiệm "một chạm").
 *
 * Liên kết trỏ tới trang người giám hộ (``guardian/index.html``, trang tĩnh). Dữ liệu nằm ở PHẦN ``#fragment``:
 * trình duyệt không bao giờ gửi fragment lên máy chủ và máy chủ/log/proxy của nơi host trang không thấy nó
 * (xem docs/GUARDIAN-MODE.md). Định dạng: ``<trang>#v=1&d=<tên miền ASCII>&n=<nonce 12 ký tự>``.
 *
 * Module thuần (không DOM, không chrome.*): dùng chung cho service worker, trang người giám hộ (đóng gói tĩnh) và kiểm thử Node.
 * @module guardian/share
 */

import { normalizeDomain, normalizeNonce } from "./codec.js";

/** Phiên bản định dạng fragment. */
export const FRAGMENT_VERSION = 1;
/** Trang người giám hộ mặc định (GitHub Pages của repo). Đổi bằng khóa managed ``guardian_page_url``. */
export const DEFAULT_PAGE_URL = "https://sanhkhoa57.github.io/CHOTTO/guardian/";
export const MAX_NAME_LENGTH = 30;
/** Ký tự điều khiển, định dạng/vô hình/đảo chiều (Cf), dùng riêng (Co), surrogate lẻ (Cs), ngắt dòng/đoạn Unicode. */
const UNSAFE_CHARS = /[\p{Cc}\p{Cf}\p{Co}\p{Cs}\p{Zl}\p{Zp}]/gu;

/**
 * Tên người giám hộ (tùy chọn, từ managed ``guardian_name``): bỏ ký tự điều khiển/vô hình, gộp khoảng trắng,
 * tối đa 30 ký tự (tính theo ký tự Unicode, không cắt đôi cặp thay thế). Người gọi gán bằng ``textContent``.
 * @param {unknown} value
 * @returns {string | null} ``null`` nếu rỗng sau khi lọc.
 */
export function sanitizeName(value) {
  if (typeof value !== "string") return null;
  const clean = value.replace(UNSAFE_CHARS, " ").replace(/\s+/g, " ").trim();
  const limited = Array.from(clean).slice(0, MAX_NAME_LENGTH).join("").trim();
  return limited === "" ? null : limited;
}

/**
 * Địa chỉ trang người giám hộ từ managed: chỉ nhận https (hoặc http tới localhost để thử), không có tài khoản/mật khẩu;
 * bỏ query và fragment. Sai thì ``null`` (người gọi dùng mặc định).
 * @param {unknown} value
 * @returns {string | null}
 */
export function sanitizePageUrl(value) {
  if (typeof value !== "string" || value.length > 512) return null;
  try {
    const url = new URL(value.trim());
    const local = url.hostname === "localhost" || url.hostname === "127.0.0.1";
    if (url.protocol !== "https:" && !(url.protocol === "http:" && local)) return null;
    if (url.username !== "" || url.password !== "") return null;
    url.search = "";
    url.hash = "";
    return url.href;
  } catch {
    return null;
  }
}

/**
 * @param {string} pageUrl Đã qua ``sanitizePageUrl``.
 * @param {string} domain Tên miền chuẩn (ASCII/punycode).
 * @param {string} nonce Nonce chuẩn (12 ký tự, không gạch).
 * @returns {string}
 */
export function buildShareLink(pageUrl, domain, nonce) {
  return `${pageUrl}#v=${FRAGMENT_VERSION}&d=${encodeURIComponent(domain)}&n=${nonce}`;
}

/**
 * Đọc fragment của liên kết trang người giám hộ.
 * @param {string} hash ``location.hash`` (có hoặc không có ``#``).
 * @returns {{ok: true, domain: string, nonce: string} | {ok: false, reason: "empty" | "version" | "domain" | "nonce"}}
 */
export function parseShareFragment(hash) {
  const text = String(hash).replace(/^#/, "");
  if (text === "") return { ok: false, reason: "empty" };
  const params = new URLSearchParams(text);
  if (params.get("v") !== String(FRAGMENT_VERSION)) return { ok: false, reason: "version" };
  const domain = normalizeDomain(params.get("d") ?? "");
  if (domain === null) return { ok: false, reason: "domain" };
  const nonce = normalizeNonce(params.get("n") ?? "");
  if (nonce === null) return { ok: false, reason: "nonce" };
  return { ok: true, domain, nonce };
}

/**
 * Viết tên trang web sao cho Zalo/ứng dụng chat KHÔNG tự biến nó thành liên kết bấm được
 * (người giám hộ lỡ chạm vào là mở thẳng trang lừa đảo): ``abc.com`` → ``abc[.]com``.
 * @param {string} domain
 * @returns {string}
 */
export function defangDomain(domain) {
  return domain.replace(/\./g, "[.]");
}

/**
 * Lời nhắn soạn sẵn để dán vào Zalo: câu ngắn + tên trang web + liên kết tới trang người giám hộ.
 * @param {{domain: string, link: string}} parts
 * @returns {string}
 */
export function buildShareMessage({ domain, link }) {
  return [
    "Mình nhận được link này, nhờ xem giúp có mở được không?",
    `Trang web: ${defangDomain(domain)}`,
    link,
  ].join("\n");
}
