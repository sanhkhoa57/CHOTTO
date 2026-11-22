// @ts-check
/**
 * Chuẩn bị nội dung màn hình "Khoan đã!" (hiển thị lũy tiến) từ kết quả thẩm định. Cùng cấu trúc và CÙNG CHỮ với
 * ``chotto/shield.py`` (bản tiếng Việt): ``tests/data/view_vectors.json`` do ``tools/gen_view_vectors.py`` sinh, cả hai
 * bên phải tái tạo đúng từng ký tự. Chữ nằm ở ``data/plain.json`` (sinh từ ``chotto/plain.py``).
 * Mọi chuỗi đều đã lọc ký tự điều khiển/đảo chiều; giao diện (``ui/shield.js``) chỉ gán bằng ``textContent``.
 * @module view
 */

import { domainToUnicode } from "./engine/punycode.js";
import { URLParseError, parseUrl } from "./engine/url.js";
import { sanitizeForDisplay } from "./engine/util.js";

const REST_LIMIT = 40;
const RAW_LIMIT = 90;
const USERINFO_LIMIT = 30;
const MAX_EDIT = 2;
const MIN_KEYWORD = 4;
const IMPERSONATION = new Set(["combosquat", "homoglyph", "typosquat"]);
const LEVELS = ["WARN", "HIGH", "BLOCKED"];

/**
 * @typedef {object} PlainData Bảng chữ đời thường (``data/plain.json``).
 * @property {Record<string, {label: string, sub: string}>} levels
 * @property {{groups: string[][], text: string}[]} combos
 * @property {Record<string, string>} single
 * @property {Record<string, string>} default
 * @property {string} brand
 * @property {Record<string, {icon: string, text: string, pattern?: string, fallback?: string}>} details
 * @property {Record<string, string>} labels
 * @property {number} max_details
 */

/**
 * @typedef {object} ShieldContext
 * @property {PlainData} plain
 * @property {import("./engine/tier2.js").Rules} rules
 */

/**
 * Kiểm tra cấu trúc ``plain.json``.
 * @param {unknown} data
 * @returns {PlainData}
 * @throws {TypeError} Sai cấu trúc.
 */
export function validatePlain(data) {
  const v = /** @type {Record<string, any>} */ (data);
  if (!v || typeof v !== "object" || !v.levels || !Array.isArray(v.combos) || !v.single || !v.default
      || !v.details || !v.labels || typeof v.brand !== "string" || !Number.isInteger(v.max_details)) {
    throw new TypeError("plain.json sai cấu trúc");
  }
  return /** @type {PlainData} */ (v);
}

/**
 * Rút gọn ở giữa (giữ đầu và cuối), đếm theo ký tự Unicode như bản Python.
 * @param {string} text
 * @param {number} limit
 * @returns {string}
 */
function truncate(text, limit) {
  const chars = Array.from(text);
  if (chars.length <= limit) return text;
  const head = Math.floor(((limit - 1) * 2) / 3);
  return `${chars.slice(0, head).join("")}…${chars.slice(chars.length - (limit - 1 - head)).join("")}`;
}

/**
 * Khoảng cách Levenshtein.
 * @param {string} a
 * @param {string} b
 * @returns {number}
 */
function levenshtein(a, b) {
  let previous = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i += 1) {
    const row = [i];
    for (let j = 1; j <= b.length; j += 1) {
      row.push(Math.min(previous[j] + 1, row[j - 1] + 1, previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)));
    }
    previous = row;
  }
  return previous[previous.length - 1];
}

/**
 * Phần của tên miền đăng ký giống tên thương hiệu nhất (để tô sáng), rỗng nếu không thấy (như ``brand_hit`` của Python).
 * @param {string} registered
 * @param {string} brand
 * @param {ShieldContext["rules"]} rules
 * @returns {string}
 */
export function brandHit(registered, brand, rules) {
  /** @type {string[]} */
  let keywords = [];
  for (const entry of /** @type {{name?: string, keywords?: string[], domains?: string[]}[]} */ (rules.brands ?? [])) {
    if (String(entry.name ?? "").toLowerCase() === brand.toLowerCase()) {
      keywords = (entry.keywords ?? []).map((k) => String(k).toLowerCase());
      break;
    }
  }
  keywords = [...keywords].sort((a, b) => b.length - a.length);
  const lowered = registered.toLowerCase();
  if (lowered.length !== registered.length) return "";
  for (const keyword of keywords) {
    const at = lowered.indexOf(keyword);
    if (at >= 0) return registered.slice(at, at + keyword.length);
  }
  let best = "";
  let bestDistance = MAX_EDIT + 1;
  for (const keyword of keywords) {
    if (keyword.length < MIN_KEYWORD) continue;
    for (const size of [keyword.length, keyword.length - 1, keyword.length + 1]) {
      for (let start = 0; start + size <= lowered.length; start += 1) {
        const distance = levenshtein(lowered.slice(start, start + size), keyword);
        if (distance < bestDistance) {
          best = registered.slice(start, start + size);
          bestDistance = distance;
        }
      }
    }
  }
  return best;
}

/**
 * Thương hiệu bị giả danh (dấu hiệu đầu tiên có ``brand``), rỗng nếu không có.
 * @param {{brand?: string}[]} signals
 * @returns {string}
 */
function brandOf(signals) {
  for (const s of signals) if (s.brand) return String(s.brand);
  return "";
}

/**
 * Tên miền chính thức đầu tiên của thương hiệu, rỗng nếu không biết.
 * @param {string} brand
 * @param {ShieldContext["rules"]} rules
 * @returns {string}
 */
function officialDomain(brand, rules) {
  for (const entry of /** @type {{name?: string, keywords?: string[], domains?: string[]}[]} */ (rules.brands ?? [])) {
    if (String(entry.name ?? "").toLowerCase() === brand.toLowerCase() && entry.domains?.length) return String(entry.domains[0]);
  }
  return "";
}

/**
 * Dấu hiệu có điểm dương, mạnh nhất trước (cùng điểm giữ thứ tự của engine).
 * @param {import("./engine/engine.js").Result} result
 */
function positive(result) {
  return result.signals
    .map((s, index) => ({ s, index }))
    .filter(({ s }) => Math.trunc(Number(s.points ?? 0)) > 0)
    .sort((a, b) => Math.trunc(Number(b.s.points)) - Math.trunc(Number(a.s.points)) || a.index - b.index)
    .map(({ s }) => s);
}

/**
 * MỘT câu kết luận: danh sách đen, kịch bản tổ hợp, dấu hiệu riêng mạnh nhất, rồi câu mặc định theo mức.
 * @param {import("./engine/engine.js").Result} result
 * @param {PlainData} plain
 * @returns {string}
 */
export function shieldHeadline(result, plain) {
  const ordered = positive(result);
  const present = new Set(ordered.map((s) => String(s.code ?? "")));
  const level = LEVELS.includes(result.level) ? result.level : "WARN";
  if (result.tierReached === 0) return plain.single.unparseable;
  if (level === "BLOCKED" && present.has("blacklist")) return plain.single.blacklist;
  for (const { groups, text } of plain.combos) {
    const hits = groups.map((group) => group.filter((code) => present.has(code)));
    if (hits.every((hit) => hit.length > 0)) {
      const matched = new Set(hits.flat());
      const found = ordered.find((s) => matched.has(String(s.code ?? "")) && s.brand);
      const brand = found ? String(found.brand) : plain.brand;
      return text.replaceAll("{brand}", () => brand);
    }
  }
  for (const s of ordered) {
    const text = Object.prototype.hasOwnProperty.call(plain.single, String(s.code ?? "")) ? plain.single[String(s.code)] : undefined;
    if (text !== undefined) return text.replaceAll("{brand}", () => String(s.brand || "") || plain.brand);
  }
  return plain.default[level];
}

/**
 * Tối đa ``max_details`` gạch đầu dòng ngắn (biểu tượng + một câu) cho mục "Xem vì sao".
 * @param {import("./engine/engine.js").Result} result
 * @param {PlainData} plain
 * @returns {{icon: string, text: string}[]}
 */
export function shieldDetails(result, plain) {
  /** @type {{icon: string, text: string}[]} */
  const rows = [];
  for (const s of positive(result)) {
    const code = String(s.code ?? "");
    if (!Object.prototype.hasOwnProperty.call(plain.details, code)) continue;
    const spec = plain.details[code];
    let text = spec.text;
    if (spec.pattern) {
      const found = new RegExp(spec.pattern, "u").exec(String(s.reason ?? ""));
      if (found) text = text.replaceAll("{0}", () => sanitizeForDisplay(found[1]));
      else if (spec.fallback !== undefined) text = spec.fallback;
      else continue;
    }
    const brand = String(s.brand || "") || plain.brand;
    rows.push({ icon: spec.icon, text: text.replaceAll("{brand}", () => brand) });
    if (rows.length === plain.max_details) break;
  }
  return rows;
}

/**
 * Tên miền thật tách thành các phần: tiền tố (nhạt), tên miền đăng ký (đậm), phần còn lại (nhạt).
 * @param {import("./engine/engine.js").Result} result
 * @param {string} brand
 * @param {ShieldContext["rules"]} rules
 */
function domainParts(result, brand, rules) {
  const empty = { userinfo: "", prefix: "", decoyPrefix: false, registered: "", rest: "", hit: "", punycode: "", isIp: false };
  const raw = result.finalUrl || result.url;
  /** @type {import("./engine/url.js").ParsedURL} */
  let url;
  try {
    url = parseUrl(raw);
  } catch (error) {
    if (!(error instanceof URLParseError)) throw error;
    return { ...empty, registered: truncate(sanitizeForDisplay(raw), RAW_LIMIT) };
  }
  const rest = (url.port !== null ? `:${url.port}` : "") + url.path + (url.query ? `?${url.query}` : "");
  const base = {
    ...empty,
    userinfo: url.username ? `${truncate(sanitizeForDisplay(url.username), USERINFO_LIMIT)}@` : "",
    rest: rest === "/" ? "" : truncate(sanitizeForDisplay(rest), REST_LIMIT),
  };
  if (url.hostKind !== "domain") return { ...base, registered: url.host, isIp: true };
  const domain = result.displayDomain || url.host;
  const prefix = url.host.endsWith(`.${domain}`) ? url.host.slice(0, url.host.length - domain.length) : "";
  const registered = sanitizeForDisplay(domainToUnicode(domain));
  const codes = new Set(result.signals.map((s) => String(s.code ?? "")));
  const hit = brand && [...codes].some((c) => IMPERSONATION.has(c)) ? brandHit(registered, brand, rules) : "";
  return {
    ...base,
    registered,
    punycode: registered !== domain ? domain : "",
    hit,
    prefix: prefix ? `${sanitizeForDisplay(domainToUnicode(prefix.replace(/\.+$/, "")))}.` : "",
    decoyPrefix: Boolean(prefix && brand),
  };
}

/**
 * Viết tên miền để không thành link bấm được khi dán vào tin nhắn: ``a.top`` → ``a[.]top``.
 * @param {string} domain
 * @returns {string}
 */
function defang(domain) {
  return domain.replaceAll(".", "[.]");
}

/**
 * Nội dung màn hình cảnh báo (xem ``chotto/shield.py`` về cấu trúc).
 * @param {import("./engine/engine.js").Result} result
 * @param {ShieldContext} context
 * @param {boolean} [checking] Tầng 3 còn chạy nền.
 */
export function buildView(result, context, checking = false) {
  const { plain, rules } = context;
  const labels = plain.labels;
  const level = LEVELS.includes(result.level) ? result.level : "WARN";
  const brand = brandOf(result.signals);
  const official = brand ? officialDomain(brand, rules) : "";
  const domain = { ...domainParts(result, brand, rules), brand, official };
  const shown = domain.registered || labels.unknown;
  return {
    lang: "vi",
    level,
    levelLabel: plain.levels[level].label,
    headline: shieldHeadline(result, plain),
    reasonShort: plain.levels[level].sub,
    domain,
    officialLine: official ? labels.official.replaceAll("{brand}", () => brand).replaceAll("{domain}", () => official) : "",
    details: shieldDetails(result, plain),
    checking,
    actions: {
      back: labels.back, proceed: labels.proceed, copy: labels.copy, report: labels.report,
      copied: labels.copied, reported: labels.reported, hint: labels.hint,
      copyText: sanitizeForDisplay(result.finalUrl || result.url),
      reportText: labels.report_text.replaceAll("{domain}", () => defang(shown)),
    },
    labels: {
      caption: labels.caption, why: labels.why, checking: labels.checking,
      proceedWait: labels.proceed_wait, decoy: labels.decoy, ip: labels.ip,
    },
  };
}
