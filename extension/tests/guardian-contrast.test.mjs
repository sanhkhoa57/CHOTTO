// @ts-check
/**
 * Đo tương phản WCAG 2.x của giao diện Guardian (màn hình trong tiện ích + trang người giám hộ), cả sáng lẫn tối.
 * Chữ thường cần >= 4,5:1 (AA); chữ lớn (>= 24px, hoặc >= 18,66px đậm) và thành phần giao diện (viền ô nhập) cần >= 3:1.
 * Màu lấy thẳng từ CSS thật (chotto/web/shield.css, guardian/src/page.css) nên đổi màu mà làm tụt tương phản sẽ làm test đỏ.
 * Đặt ``PRINT_CONTRAST=1`` để in bảng markdown (đã dán vào docs/GUARDIAN-MODE.md).
 */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

import { EXTENSION_DIR, REPO_DIR } from "./helpers.mjs";

/** @typedef {[number, number, number, number]} Rgba */

/**
 * @param {string} value
 * @returns {Rgba}
 */
function parseColor(value) {
  const v = value.trim();
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(v);
  if (hex) {
    const h = hex[1].length === 3 ? [...hex[1]].map((c) => c + c).join("") : hex[1];
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), 1];
  }
  const rgba = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)$/.exec(v);
  if (rgba) return [Number(rgba[1]), Number(rgba[2]), Number(rgba[3]), rgba[4] === undefined ? 1 : Number(rgba[4])];
  throw new Error(`không hiểu màu: ${value}`);
}

/**
 * @param {Rgba} top
 * @param {Rgba} bottom
 * @returns {Rgba}
 */
function over(top, bottom) {
  const a = top[3];
  return [0, 1, 2].map((i) => top[i] * a + bottom[i] * (1 - a)).concat([1]);
}

/** @param {Rgba} c */
function luminance(c) {
  const [r, g, b] = [c[0], c[1], c[2]].map((x) => {
    const s = x / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/**
 * @param {Rgba} fg
 * @param {Rgba} bg
 */
function ratio(fg, bg) {
  const solid = fg[3] < 1 ? over(fg, bg) : fg;
  const [hi, lo] = [luminance(solid), luminance(bg)].sort((a, b) => b - a);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Biến CSS trong một khối ``{ ... }``.
 * @param {string} block
 * @returns {Record<string, string>}
 */
function vars(block) {
  /** @type {Record<string, string>} */
  const out = {};
  for (const m of block.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}

/**
 * @param {string} css
 * @param {string} opener Phần đứng trước dấu { của khối cần lấy (ví dụ ".sh {").
 */
function blockAfter(css, opener) {
  const start = css.indexOf(opener);
  assert.ok(start >= 0, `không thấy khối ${opener}`);
  let depth = 0;
  for (let i = css.indexOf("{", start); i < css.length; i++) {
    if (css[i] === "{") depth++;
    if (css[i] === "}" && --depth === 0) return css.slice(css.indexOf("{", start) + 1, i);
  }
  throw new Error("khối CSS không đóng");
}

const shieldCss = await readFile(path.join(REPO_DIR, "chotto", "web", "shield.css"), "utf-8");   // nguồn của shield-css.js
const pageCss = await readFile(path.join(REPO_DIR, "guardian", "src", "page.css"), "utf-8");

/** @type {Record<string, Record<string, string>>} */
const themes = {
  "tiện ích · tối": vars(blockAfter(shieldCss, ".sh {")),
  "tiện ích · sáng": { ...vars(blockAfter(shieldCss, ".sh {")), ...vars(blockAfter(shieldCss, '.sh[data-theme="light"] {')) },
  "trang người giám hộ · sáng": vars(blockAfter(pageCss, ":root {")),
  "trang người giám hộ · tối": { ...vars(blockAfter(pageCss, ":root {")), ...vars(blockAfter(blockAfter(pageCss, "@media (prefers-color-scheme: dark) {"), ":root {")) },
};

/** @type {[string, string, string, number, string[]][]} nhãn, màu chữ, màu nền, mức tối thiểu, các chủ đề áp dụng */
const SHIELD = ["tiện ích · tối", "tiện ích · sáng"];
const PAGE = ["trang người giám hộ · sáng", "trang người giám hộ · tối"];
const PAIRS = [
  ["chữ chính trên nền", "ink", "bg", 4.5, [...SHIELD, ...PAGE]],
  ["chữ chính trên thẻ", "ink", "surface", 4.5, [...SHIELD, ...PAGE]],
  ["chữ chính trên nút phụ", "ink", "surface2", 4.5, [...SHIELD, ...PAGE]],
  ["chữ phụ trên nền", "muted", "bg", 4.5, [...SHIELD, ...PAGE]],
  ["chữ phụ trên thẻ", "muted", "surface", 4.5, [...SHIELD, ...PAGE]],
  ["chữ trên nút chính", "accent-ink", "accent", 4.5, [...SHIELD, ...PAGE]],
  ["nhãn mức HIGH", "high-ink", "bg", 4.5, SHIELD],
  ["nhãn mức BLOCKED", "blocked-ink", "bg", 4.5, SHIELD],
  ["nhãn mức WARN / nhắc hạn", "warn-ink", "bg", 4.5, SHIELD],
  ["chữ cảnh báo đỏ trên nền đỏ nhạt", "danger-ink", "danger-bg", 4.5, PAGE],
  ["chữ cảnh báo vàng trên nền vàng nhạt", "warn-ink", "warn-bg", 4.5, PAGE],
  ["chữ 'an toàn' trên nền xanh nhạt", "ok-ink", "ok-bg", 4.5, PAGE],
  ["viền ô nhập / thẻ (thành phần giao diện)", "line", "bg", 3, PAGE],
  ["viền khung tiêu điểm", "focus", "bg", 3, PAGE],
  ["viền ô nhập (tiện ích: 62% màu chữ)", "edge", "bg", 3, SHIELD],
];

/** Viền ô nhập của tiện ích = trộn 62% màu chữ với màu nền (xem guardian-css.js: --gd-edge). */
for (const name of SHIELD) {
  const t = themes[name];
  const ink = parseColor(t.ink);
  const bg = parseColor(t.bg);
  t.edge = `rgb(${[0, 1, 2].map((i) => Math.round(ink[i] * 0.62 + bg[i] * 0.38)).join(",")})`.replace("rgb(", "rgba(").replace(")", ",1)");
}

/** @type {string[]} */
const rows = [];

test("tương phản WCAG AA của Guardian (sáng và tối, tiện ích và trang người giám hộ)", () => {
  for (const [label, fg, bg, min, applies] of PAIRS) {
    for (const name of applies) {
      const theme = themes[name];
      assert.ok(theme[fg] && theme[bg], `${name}: thiếu biến ${fg}/${bg}`);
      const value = ratio(parseColor(theme[fg]), parseColor(theme[bg]));
      rows.push(`| ${label} | ${name} | \`${theme[fg]}\` / \`${theme[bg]}\` | ${value.toFixed(2)}:1 | ${min}:1 | ${value >= min ? "đạt" : "KHÔNG đạt"} |`);
      assert.ok(value >= min, `${label} (${name}): ${value.toFixed(2)}:1 < ${min}:1`);
    }
  }
  if (process.env.PRINT_CONTRAST) {
    console.log("| Cặp màu | Chủ đề | Chữ / nền | Đo được | Cần | Kết quả |\n|---|---|---|---|---|---|\n" + rows.join("\n"));
  }
});
