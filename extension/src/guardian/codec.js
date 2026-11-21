// @ts-check
/**
 * Các hàm mật mã/mã hóa của Guardian mode. KHÔNG tự cài thuật toán mật mã: HMAC-SHA256, SHA-256, Ed25519 và số
 * ngẫu nhiên đều của WebCrypto; ở đây chỉ có phần "keo" (base32/base64url, cắt bớt kiểu HOTP, so sánh thời gian hằng).
 * Chạy được cả trong service worker lẫn Node (``globalThis.crypto``).
 * @module guardian/codec
 */

/** Tiền tố ngữ cảnh gắn vào thông điệp HMAC (tách miền với mọi cách dùng khóa khác). */
export const CODE_CONTEXT = "CHOTTO-GUARDIAN-v1";
/** Tiền tố ngữ cảnh khi ký chính sách Ed25519. */
export const POLICY_CONTEXT = "CHOTTO-GUARDIAN-POLICY-v1\n";
export const CODE_DIGITS = 6;
export const NONCE_BYTES = 5; // 40 bit
const BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

const encoder = new TextEncoder();

/**
 * Base64url (không đệm) → byte. Chấp nhận cả base64 thường và có đệm.
 * @param {string} text
 * @returns {Uint8Array}
 * @throws {Error} Không phải base64 hợp lệ.
 */
export function fromBase64Url(text) {
  if (typeof text !== "string" || !/^[A-Za-z0-9_\-+/]*={0,2}$/.test(text)) throw new Error("base64 không hợp lệ");
  const std = text.replace(/-/g, "+").replace(/_/g, "/").replace(/=+$/, "");
  if (std.length % 4 === 1) throw new Error("base64 không hợp lệ");
  const raw = atob(std + "=".repeat((4 - (std.length % 4)) % 4));
  return Uint8Array.from(raw, (ch) => ch.charCodeAt(0));
}

/**
 * @param {Uint8Array} bytes
 * @returns {string} Base64url không đệm.
 */
export function toBase64Url(bytes) {
  let raw = "";
  for (const b of bytes) raw += String.fromCharCode(b);
  return btoa(raw).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/**
 * @param {Uint8Array} bytes Độ dài là bội của 5 (không đệm).
 * @returns {string} Base32 (RFC 4648, chữ hoa, không đệm).
 */
export function toBase32(bytes) {
  let bits = 0;
  let value = 0;
  let out = "";
  for (const b of bytes) {
    value = (value << 8) | b;
    bits += 8;
    while (bits >= 5) {
      out += BASE32[(value >>> (bits - 5)) & 31];
      bits -= 5;
    }
  }
  if (bits > 0) out += BASE32[(value << (5 - bits)) & 31];
  return out;
}

/**
 * Nonce ngẫu nhiên 40 bit, dạng base32 8 ký tự (ví dụ ``K7QF3MZD``).
 * @param {(n: number) => Uint8Array} [random]
 * @returns {string}
 */
export function newNonce(random = (n) => crypto.getRandomValues(new Uint8Array(n))) {
  return toBase32(random(NONCE_BYTES));
}

/**
 * @param {string} nonce 8 ký tự base32.
 * @returns {string} ``K7QF-3MZD``.
 */
export function formatNonce(nonce) {
  return `${nonce.slice(0, 4)}-${nonce.slice(4)}`;
}

/**
 * Chuẩn hóa nonce người dùng gõ/dán: bỏ khoảng trắng và gạch, chữ hoa. ``null`` nếu sai dạng.
 * @param {string} text
 * @returns {string | null}
 */
export function normalizeNonce(text) {
  const clean = String(text).replace(/[\s-]/g, "").toUpperCase();
  return /^[A-Z2-7]{8}$/.test(clean) ? clean : null;
}

/**
 * Tên miền chuẩn: chữ thường, không dấu chấm cuối, chỉ ký tự ASCII hợp lệ (tên miền Unicode phải ở dạng punycode).
 * @param {string} text
 * @returns {string | null}
 */
export function normalizeDomain(text) {
  const clean = String(text).trim().toLowerCase().replace(/\.$/, "");
  return /^[a-z0-9.\-:[\]]{1,253}$/.test(clean) && !clean.includes("|") ? clean : null;
}

/**
 * Thông điệp HMAC: ``CHOTTO-GUARDIAN-v1|<tên miền>|<nonce>``. Cũng là nội dung mã QR.
 * @param {string} domain Đã chuẩn hóa.
 * @param {string} nonce Đã chuẩn hóa.
 * @returns {string}
 */
export function challengeMessage(domain, nonce) {
  return `${CODE_CONTEXT}|${domain}|${nonce}`;
}

/**
 * HOTP dynamic truncation (RFC 4226 §5.3) trên HMAC-SHA256.
 * @param {Uint8Array} mac
 * @returns {string} 6 chữ số.
 */
export function truncate(mac) {
  const offset = mac[mac.length - 1] & 0x0f;
  const binary = ((mac[offset] & 0x7f) << 24) | (mac[offset + 1] << 16) | (mac[offset + 2] << 8) | mac[offset + 3];
  return String(binary % 10 ** CODE_DIGITS).padStart(CODE_DIGITS, "0");
}

/**
 * Mã mở khóa 6 số cho (tên miền, nonce).
 * @param {Uint8Array} secret
 * @param {string} domain
 * @param {string} nonce
 * @returns {Promise<string>}
 */
export async function computeCode(secret, domain, nonce) {
  const key = await crypto.subtle.importKey("raw", /** @type {BufferSource} */ (secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(challengeMessage(domain, nonce))));
  return truncate(mac);
}

/**
 * So sánh chuỗi không phụ thuộc vị trí khác biệt đầu tiên (chống đo thời gian).
 * @param {string} a
 * @param {string} b
 * @returns {boolean}
 */
export function constantTimeEqual(a, b) {
  const x = encoder.encode(a);
  const y = encoder.encode(b);
  let diff = x.length ^ y.length;
  const n = Math.max(x.length, y.length);
  for (let i = 0; i < n; i++) diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return diff === 0;
}

/**
 * @param {string} text
 * @returns {Promise<string>} SHA-256 dạng hex.
 */
export async function sha256Hex(text) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(text)));
  return Array.from(digest, (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Xác minh chữ ký Ed25519 lên chính sách. Trả ``false`` khi sai chữ ký HOẶC khi môi trường không hỗ trợ Ed25519
 * (fail-closed: không bao giờ coi là hợp lệ khi không xác minh được).
 * @param {Uint8Array} publicKey 32 byte thô.
 * @param {string} payload Chuỗi JSON đúng từng byte đã được ký.
 * @param {Uint8Array} signature 64 byte.
 * @returns {Promise<boolean>}
 */
export async function verifyPolicySignature(publicKey, payload, signature) {
  try {
    if (publicKey.length !== 32 || signature.length !== 64) return false;
    const key = await crypto.subtle.importKey("raw", /** @type {BufferSource} */ (publicKey), { name: "Ed25519" }, false, ["verify"]);
    return await crypto.subtle.verify({ name: "Ed25519" }, key, /** @type {BufferSource} */ (signature), encoder.encode(POLICY_CONTEXT + payload));
  } catch {
    return false;
  }
}
