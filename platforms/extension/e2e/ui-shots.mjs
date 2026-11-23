// @ts-check
/**
 * Chụp màn hình cảnh báo "Khoan đã!" của tiện ích cho 4 ca (WARN, HIGH, BLOCKED, IDN) ở chế độ tối/sáng và cỡ điện thoại.
 * Mở trang cảnh báo của chính tiện ích (``warn.html?u=``) nên ảnh chụp đúng giao diện thật, qua service worker thật.
 *
 * Chạy: ``node e2e/ui-shots.mjs <thư mục ảnh> [tiền tố tên file]``
 */
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const EXTENSION_DIR = process.env.EXTENSION_DIR || path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const CASES = [
  ["warn", "https://khuyen-mai-hoan-tien.shop/uu-dai"],
  ["high", "https://vcb-digibanks.top/xac-nhan"],
  ["blocked", "https://momo-hoantien.vip/nhan-qua"],
  ["idn", "https://vietcombаnk.com/dang-nhap"],
];

/**
 * @param {string} outDir
 * @param {string} prefix
 * @returns {Promise<void>}
 */
async function main(outDir, prefix) {
  await mkdir(outDir, { recursive: true });
  const profile = await mkdtemp(path.join(os.tmpdir(), "chotto-ui-"));
  const context = await chromium.launchPersistentContext(profile, {
    channel: "chromium",
    executablePath: process.env.CHROMIUM_PATH || undefined,
    headless: true,
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 2,
    locale: "vi-VN",
    colorScheme: "dark",
    args: [`--disable-extensions-except=${EXTENSION_DIR}`, `--load-extension=${EXTENSION_DIR}`],
  });
  try {
    let [worker] = context.serviceWorkers();
    if (!worker) worker = await context.waitForEvent("serviceworker");
    const id = new URL(worker.url()).host;
    const options = await context.newPage();
    await options.goto(`chrome-extension://${id}/src/ui/options.html`);
    await options.evaluate(() => chrome.runtime.sendMessage({
      type: "settings", changes: { tier3Enabled: false, autoUpdate: false, frictionSeconds: 6 },
    }));
    await options.close();
    for (const [scheme, size, tag] of /** @type {const} */ ([["dark", [1280, 800], ""], ["light", [1280, 800], "-sang"], ["dark", [390, 780], "-dien-thoai"]])) {
      for (const [name, url] of CASES) {
        const page = await context.newPage();
        await page.setViewportSize({ width: size[0], height: size[1] });
        await page.emulateMedia({ colorScheme: scheme });
        await page.goto(`chrome-extension://${id}/src/ui/warn.html?u=${encodeURIComponent(url)}`);
        await page.waitForTimeout(1600);
        await page.screenshot({ path: path.join(outDir, `${prefix}${name}${tag}.png`) });
        await page.close();
      }
    }
  } finally {
    await context.close();
    await rm(profile, { recursive: true, force: true });
  }
}

main(process.argv[2] ?? path.join(EXTENSION_DIR, "screenshots"), process.argv[3] ?? "").catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
