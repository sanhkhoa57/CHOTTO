// @ts-check
/** Trang tùy chọn: cài đặt, trạng thái danh sách đen, thử liên kết, nhật ký quyết định. */

const CHOICES = Object.freeze({ back: "Đóng, không mở", blocked_back: "Đóng (danh sách đen)", proceed: "Vẫn mở" });
const VIA = Object.freeze({ click: "Bấm link", "window.open": "Script của Zalo", "tab-moi": "Tab mới" });
const LEVELS = Object.freeze({ SAFE: "An toàn", WARN: "Đáng ngờ", HIGH: "Rất nguy hiểm", BLOCKED: "Danh sách đen" });

/**
 * @param {string} id
 * @returns {HTMLElement}
 */
function byId(id) {
  const node = document.getElementById(id);
  if (!node) throw new Error(`Thiếu phần tử #${id}`);
  return node;
}

/**
 * @param {Record<string, unknown>} message
 * @returns {Promise<any>}
 * @throws {Error} Service worker trả lỗi.
 */
async function ask(message) {
  const reply = await chrome.runtime.sendMessage(message);
  if (!reply || reply.ok !== true) throw new Error(reply?.error ?? "Không có phản hồi từ CHOTTO");
  return reply.value;
}

/**
 * @param {number | undefined | null} ms
 * @returns {string}
 */
function formatTime(ms) {
  return typeof ms === "number" ? new Date(ms).toLocaleString("vi-VN") : "chưa có";
}

/**
 * @param {unknown} error
 * @returns {string}
 */
function message(error) {
  return error instanceof Error ? error.message : String(error);
}

const LEVEL_NAMES = Object.freeze({ WARN: "Đáng ngờ", HIGH: "Rất nguy hiểm", BLOCKED: "Danh sách đen" });

/**
 * Trạng thái Guardian, chỉ đọc (nguồn: ``chrome.storage.managed`` + chính sách ký đã xác minh).
 * @param {any} g
 */
function renderGuardian(g) {
  const state = byId("guardian-state");
  const details = byId("guardian-details");
  const warnings = byId("guardian-warnings");
  const form = byId("guardian-import");
  state.dataset.mode = g.mode;
  details.replaceChildren();
  warnings.replaceChildren();
  form.hidden = g.mode === "off";
  if (g.mode === "off") {
    state.textContent = "Đang tắt. Chế độ người giám hộ chỉ bật bằng chính sách quản lý của máy (Administrator).";
    details.hidden = true;
    warnings.hidden = true;
    return;
  }
  state.textContent = g.mode === "ok"
    ? "Đang bật bởi chính sách quản lý (managed storage)."
    : "Đang bật nhưng cấu hình quản lý thiếu/hỏng bí mật: mọi link nguy hiểm bị chặn và không ai mở khóa được cho tới khi sửa.";
  const policy = g.policySource === "signed"
    ? `Chính sách đã ký hợp lệ, phiên bản ${g.policyVersion}`
    : "Mặc định nghiêm nhất (không có chính sách ký hợp lệ)";
  /** @type {[string, string][]} */
  const rows = [
    ["Chính sách", policy],
    ["Phiên bản tối thiểu (managed)", String(g.minPolicyVersion)],
    ["Mức cần xin phép", g.requireLevels.map((/** @type {string} */ l) => /** @type {Record<string, string>} */ (LEVEL_NAMES)[l] ?? l).join(", ")],
    ["Tên miền luôn cho phép", g.allowDomains.length ? g.allowDomains.join(", ") : "không có"],
    ["Hạn thử thách", `${Math.round(g.ttlSeconds / 60)} phút`],
    ["Thử thách đang chờ", String(g.pending)],
    ["Khóa tạm", g.lockedUntil ? `đến ${formatTime(g.lockedUntil)}` : "không"],
  ];
  if (g.policyProblem) rows.splice(1, 0, ["Chính sách ký bị bỏ qua", g.policyProblem]);
  for (const [name, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = name;
    const dd = document.createElement("dd");
    dd.textContent = value;
    details.append(dt, dd);
  }
  details.hidden = false;
  for (const w of g.warnings) {
    const item = document.createElement("li");
    item.textContent = `${formatTime(w.ts)}: ${w.msg}`;
    warnings.append(item);
  }
  warnings.hidden = g.warnings.length === 0;
}

/** Nạp trạng thái và đổ vào form. */
async function refreshStatus() {
  const status = await ask({ type: "status" });
  byId("version").textContent = status.version;
  renderGuardian(status.guardian);
  const form = /** @type {HTMLFormElement} */ (byId("settings"));
  for (const [key, value] of Object.entries(status.settings)) {
    const input = /** @type {HTMLInputElement | null} */ (form.elements.namedItem(key));
    if (!input) continue;
    if (input.type === "checkbox") input.checked = Boolean(value);
    else input.value = String(value);
  }
  const bl = status.blacklist;
  byId("blacklist").textContent = bl
    ? `${bl.count.toLocaleString("vi-VN")} mục · dựng lúc ${formatTime(bl.builtAt)} (${bl.origin === "seed" ? "danh sách khởi tạo" : "đã cập nhật"})`
    : "Chưa có danh sách đen.";
  const update = status.update;
  byId("update").textContent = `Nguồn: ${status.sources.join(", ")}. Lần cập nhật thành công gần nhất: `
    + `${formatTime(update?.lastSuccess)}; lần thử gần nhất: ${formatTime(update?.lastAttempt)}.`;
}

/** Vẽ bảng nhật ký. */
async function refreshLog() {
  const { decisions } = await ask({ type: "log", limit: 300 });
  const body = byId("log");
  body.replaceChildren();
  if (!decisions.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "muted";
    cell.textContent = "Chưa có quyết định nào.";
    row.append(cell);
    body.append(row);
    return;
  }
  for (const d of decisions) {
    const row = document.createElement("tr");
    const cells = [
      formatTime(d.ts), d.domain, /** @type {Record<string, string>} */ (LEVELS)[d.level] ?? d.level, String(d.score),
      /** @type {Record<string, string>} */ (CHOICES)[d.choice] ?? d.choice, /** @type {Record<string, string>} */ (VIA)[d.via] ?? d.via,
    ];
    cells.forEach((text, index) => {
      const cell = document.createElement("td");
      cell.textContent = text;
      if (index === 1) cell.className = "domain";
      if (index === 2) cell.className = `level-${d.level}`;
      row.append(cell);
    });
    body.append(row);
  }
}

byId("settings").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = /** @type {HTMLFormElement} */ (event.currentTarget);
  const out = byId("settings-status");
  /** @type {Record<string, boolean | number>} */
  const changes = {};
  for (const element of Array.from(form.elements)) {
    const input = /** @type {HTMLInputElement} */ (element);
    if (!input.name) continue;
    changes[input.name] = input.type === "checkbox" ? input.checked : Number(input.value);
  }
  try {
    await ask({ type: "settings", changes });
    out.textContent = "Đã lưu cài đặt.";
  } catch (error) {
    out.textContent = `Không lưu được: ${message(error)}`;
  }
});

byId("guardian-import").addEventListener("submit", async (event) => {
  event.preventDefault();
  const out = byId("guardian-import-status");
  const box = /** @type {HTMLTextAreaElement} */ (byId("guardian-policy"));
  try {
    const answer = await ask({ type: "guardian-import", text: box.value });
    out.textContent = answer.ok ? `Đã nhận chính sách phiên bản ${answer.version}.` : `Không nhận: ${answer.error}`;
    if (answer.ok) box.value = "";
    await refreshStatus();
  } catch (error) {
    out.textContent = `Không nhập được: ${message(error)}`;
  }
});

byId("update-now").addEventListener("click", async (event) => {
  const button = /** @type {HTMLButtonElement} */ (event.currentTarget);
  const out = byId("update-status");
  button.disabled = true;
  out.textContent = "Đang tải các nguồn danh sách đen…";
  try {
    const outcome = await ask({ type: "update-now" });
    out.textContent = outcome.log.join("\n");
    await refreshStatus();
  } catch (error) {
    out.textContent = `Cập nhật lỗi: ${message(error)}`;
  } finally {
    button.disabled = false;
  }
});

byId("test").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = /** @type {HTMLFormElement} */ (event.currentTarget);
  const out = byId("test-status");
  const url = /** @type {HTMLInputElement} */ (form.elements.namedItem("url")).value;
  out.textContent = "Đang kiểm tra…";
  try {
    const { view, level, score, elapsedMs } = await ask({ type: "test", url });
    const lines = [`${/** @type {Record<string, string>} */ (LEVELS)[level] ?? level} · ${score}/100 · ${elapsedMs} ms`,
      view.headline, view.domain.registered, ...view.details.map((/** @type {{text: string}} */ r) => `• ${r.text}`)];
    out.textContent = lines.join("\n");
  } catch (error) {
    out.textContent = `Không kiểm tra được: ${message(error)}`;
  }
});

byId("log-clear").addEventListener("click", async () => {
  const out = byId("log-status");
  try {
    await ask({ type: "log-clear" });
    out.textContent = "Đã xóa nhật ký.";
    await refreshLog();
  } catch (error) {
    out.textContent = `Không xóa được: ${message(error)}`;
  }
});

Promise.all([refreshStatus(), refreshLog()]).catch((error) => {
  byId("settings-status").textContent = `Không nạp được trạng thái: ${message(error)}`;
});
