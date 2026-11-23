// @ts-check
/**
 * Màn hình cảnh báo: ``view.js`` phải cho đúng cấu trúc và đúng chữ của ``chotto/shield.py`` trên mọi vector trong
 * ``tests/data/view_vectors.json`` (sinh bởi ``tools/gen_view_vectors.py``), và đáp ứng các ràng buộc "ngắn, đời thường".
 */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

import { buildView } from "../src/view.js";
import { REPO_DIR, makeEngine } from "./helpers.mjs";

/**
 * @param {Record<string, any>} view
 * @returns {Record<string, any>}
 */
function comparable(view) {
  const { labels, actions, lang, ...rest } = view;
  void labels;
  void lang;
  return { ...rest, actions: { copyText: actions.copyText, reportText: actions.reportText } };
}

test("view JS khớp view Python trên toàn bộ vector dùng chung", async () => {
  const payload = JSON.parse(await readFile(path.join(REPO_DIR, "tests", "data", "view_vectors.json"), "utf-8"));
  const { engine, data } = await makeEngine();
  const context = { plain: data.plain, rules: data.rules };
  const mismatches = [];
  for (const expected of payload.vectors) {
    const actual = comparable(buildView(await engine.inspect(expected.url), context));
    try {
      assert.deepStrictEqual(actual, expected.view);
    } catch {
      mismatches.push({ url: expected.url, expected: expected.view, actual });
    }
  }
  for (const { url, expected, actual } of mismatches.slice(0, 8)) {
    console.error("URL:", url);
    for (const key of Object.keys(expected)) {
      if (JSON.stringify(expected[key]) !== JSON.stringify(actual[key])) {
        console.error(`  ${key}: py=${JSON.stringify(expected[key])}\n  ${" ".repeat(key.length)}  js=${JSON.stringify(actual[key])}`);
      }
    }
  }
  assert.equal(mismatches.length, 0, `${mismatches.length}/${payload.vectors.length} vector lệch`);
  assert.ok(payload.vectors.length > 100);
});

test("câu kết luận ngắn, chi tiết tối đa 3 dòng, không có thuật ngữ kỹ thuật", async () => {
  const payload = JSON.parse(await readFile(path.join(REPO_DIR, "tests", "data", "view_vectors.json"), "utf-8"));
  const banned = /(tầng|heuristic|điểm|signal|combosquat|tld|rdap|punycode)/i;
  for (const { url, view } of payload.vectors) {
    assert.ok(view.headline.split(/\s+/).length <= 12, `${url}: câu kết luận quá dài: ${view.headline}`);
    assert.ok(view.details.length <= 3, url);
    for (const text of [view.headline, view.reasonShort, view.levelLabel, ...view.details.map((/** @type {any} */ d) => d.text)]) {
      assert.doesNotMatch(text, banned, `${url}: ${text}`);
    }
  }
});

test("tên miền giả danh: tách phần thật, tô sáng phần giống thương hiệu, ghi tên miền chính thức", async () => {
  const { engine, data } = await makeEngine();
  const context = { plain: data.plain, rules: data.rules };
  const view = buildView(await engine.inspect("https://vcb-digibanks.top/xac-nhan"), context);
  assert.equal(view.headline, "Giả danh Vietcombank và hối thúc bạn");
  assert.deepEqual([view.domain.registered, view.domain.hit, view.domain.rest], ["vcb-digibanks.top", "vcb", "/xac-nhan"]);
  assert.equal(view.officialLine, "Trang chính thức của Vietcombank là vietcombank.com.vn");
  const sub = buildView(await engine.inspect("https://vietcombank.com.vn.xacthuc-tk.top/khoa-tai-khoan"), context);
  assert.equal(sub.domain.prefix, "vietcombank.com.vn.");
  assert.equal(sub.domain.decoyPrefix, true);
  assert.equal(sub.domain.registered, "xacthuc-tk.top");
  assert.match(sub.actions.reportText, /xacthuc-tk\[\.\]top$/);
});
