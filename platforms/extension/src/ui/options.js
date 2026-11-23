// @ts-check
/**
 * Trang cài đặt của tiện ích, giao diện y như cửa sổ ứng dụng Desktop: Tổng quan, Kiểm tra link, Nhật ký, Cài đặt.
 * Dữ liệu lấy từ service worker qua ``chrome.runtime.sendMessage`` (status, log, test, settings, update-now...).
 * Mọi chữ lấy từ dữ liệu đều đi qua ``textContent`` hoặc ``esc``; không bao giờ gán thẳng vào innerHTML.
 */

const LEVEL_NAMES = Object.freeze({ WARN: "Đáng ngờ", HIGH: "Rất nguy hiểm", BLOCKED: "Danh sách đen" });
const WEEK_MS = 7 * 24 * 3600 * 1000;
const OK_ICON = '<span class="ok" aria-hidden="true"><svg viewBox="0 0 16 16"><path d="m3.5 8.4 2.8 2.8 6.2-6.4"/></svg></span>';
const ICO = {
  ok: '<svg viewBox="0 0 24 24"><path d="M12 3l8 3v6c0 4.5-3.3 8-8 9-4.7-1-8-4.5-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/></svg>',
  warn: '<svg viewBox="0 0 24 24"><path d="M12 3.5 22 20.5H2z"/><path d="M12 10v4.5M12 17.4h.01"/></svg>',
  high: '<svg viewBox="0 0 24 24"><path d="M8.2 3h7.6L21 8.2v7.6L15.8 21H8.2L3 15.8V8.2z"/><path d="M12 7.5v5.5M12 16.5h.01"/></svg>',
};
const GLYPH = {
  ok: '<svg class="glyph" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  warn: '<svg class="glyph" viewBox="0 0 24 24"><path d="M12 5v9M12 18.5h.01"/></svg>',
};
// Tem tròn có viền lượn sóng, giống thẻ trạng thái của app Desktop.
const BURST = (() => {
  let d = "";
  for (let i = 0; i <= 120; i++) {
    const a = (i / 120) * Math.PI * 2;
    const r = 45 + 3.6 * Math.cos(a * 12);
    d += `${i ? "L" : "M"}${(50 + r * Math.cos(a)).toFixed(1)} ${(50 + r * Math.sin(a)).toFixed(1)}`;
  }
  return `<svg viewBox="0 0 100 100"><path class="burst" d="${d}Z"/></svg>`;
})();

/**
 * @param {string} selector
 * @returns {HTMLElement}
 */
function $(selector) {
  const node = /** @type {HTMLElement | null} */ (document.querySelector(selector));
  if (!node) throw new Error(`Thiếu phần tử ${selector}`);
  return node;
}

/**
 * @param {string} selector
 * @returns {HTMLElement[]}
 */
function $$(selector) {
  return /** @type {HTMLElement[]} */ ([...document.querySelectorAll(selector)]);
}

/**
 * @param {unknown} value
 * @returns {string}
 */
function esc(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c);
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

let toastTimer = 0;
/**
 * @param {string} text
 * @param {boolean} [isError]
 */
function toast(text, isError = false) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.toggle("err", isError);
  el.classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => el.classList.remove("on"), isError ? 5000 : 2200);
}

/**
 * "Hôm nay, 15:20" / "Hôm qua, 15:20" / "12/11, 15:20".
 * @param {number} ms
 * @returns {string}
 */
function when(ms) {
  const d = new Date(ms);
  const hm = d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  const days = Math.round((new Date(new Date().toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 86400000);
  if (days === 0) return `Hôm nay, ${hm}`;
  if (days === 1) return `Hôm qua, ${hm}`;
  return `${d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" })}, ${hm}`;
}

/**
 * Nhãn của một quyết định trong nhật ký, cùng ngôn ngữ nhãn với app Desktop.
 * @param {{level: string, choice: string}} d
 * @returns {string}
 */
function chip(d) {
  if (d.choice === "blocked_back") return '<span class="chip high">Đã chặn</span>';
  const label = d.level === "SAFE" ? "An toàn" : d.choice === "proceed" ? "Bạn vẫn mở" : "Bạn đã đóng";
  const tone = d.level === "SAFE" ? "ok" : d.level === "WARN" ? "warn" : "high";
  return `<span class="chip ${tone}">${label}</span>`;
}

/**
 * @param {{ts: number, domain: string, level: string, choice: string}[]} rows
 * @returns {string}
 */
function rowsHTML(rows) {
  if (!rows.length) return '<p class="empty">Chưa có link nào.</p>';
  return rows.map((r) => `<div class="row"><span class="d">${esc(r.domain)}</span><span class="t">${esc(when(r.ts))}</span>${chip(r)}</div>`).join("");
}

/**
 * Trạng thái Guardian, chỉ đọc (nguồn: ``chrome.storage.managed`` + chính sách ký đã xác minh).
 * @param {any} g
 */
function renderGuardian(g) {
  const state = $("#guardian-state");
  const details = $("#guardian-details");
  const warnings = $("#guardian-warnings");
  state.dataset.mode = g.mode;
  details.replaceChildren();
  warnings.replaceChildren();
  $("#guardian-import").hidden = g.mode === "off";
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

/**
 * Thẻ trạng thái ở Tổng quan.
 * @param {any} status
 */
function renderGuard(status) {
  const mode = status.guardian.mode;
  const bad = mode === "misconfigured";
  $("#guard").classList.toggle("off", bad);
  $("#guardTitle").textContent = bad ? "Cấu hình người giám hộ bị lỗi" : "Zalo Web đang được bảo vệ";
  $("#guardBadge").hidden = mode !== "ok";
  $("#guardIco").innerHTML = BURST + (bad ? GLYPH.warn : GLYPH.ok);
  const bl = status.blacklist;
  $("#guardText").textContent = bl ? `${bl.count.toLocaleString("vi-VN")} link lừa đảo trong danh sách, cập nhật ${when(bl.builtAt).toLowerCase()}` : "Chưa có danh sách lừa đảo.";
}

/** Nạp trạng thái và đổ vào giao diện. */
async function refreshStatus() {
  const status = await ask({ type: "status" });
  $("#version").textContent = status.version;
  renderGuardian(status.guardian);
  renderGuard(status);
  for (const sw of $$(".switch[data-key]")) sw.setAttribute("aria-checked", String(Boolean(status.settings[sw.dataset.key ?? ""])));
  for (const input of $$("input.num[data-key]")) /** @type {HTMLInputElement} */ (input).value = String(status.settings[input.dataset.key ?? ""]);
  for (const b of $$("#seconds button")) b.setAttribute("aria-pressed", String(Number(b.dataset.s) === status.settings.frictionSeconds));
  const bl = status.blacklist;
  $("#blacklist").textContent = bl
    ? `${bl.count.toLocaleString("vi-VN")} mục · dựng lúc ${formatTime(bl.builtAt)} (${bl.origin === "seed" ? "danh sách khởi tạo" : "đã cập nhật"})`
    : "Chưa có danh sách đen.";
  const update = status.update;
  $("#update").textContent = `Nguồn: ${status.sources.join(", ")}. Cập nhật thành công gần nhất: ${formatTime(update?.lastSuccess)}.`;
  return status.settings;
}

/** Nhật ký → Tổng quan (số liệu 7 ngày, gần đây) và mục Nhật ký. */
async function refreshLog(logging = true) {
  const { decisions } = await ask({ type: "log", limit: 300 });
  const since = Date.now() - WEEK_MS;
  const week = decisions.filter((/** @type {{ts: number}} */ d) => d.ts >= since);
  const safe = week.filter((/** @type {{level: string}} */ d) => d.level === "SAFE").length;
  const blocked = week.filter((/** @type {{level: string}} */ d) => d.level === "BLOCKED").length;
  const warnedRows = week.filter((/** @type {{level: string}} */ d) => d.level === "WARN" || d.level === "HIGH");
  const closed = warnedRows.filter((/** @type {{choice: string}} */ d) => d.choice !== "proceed").length;
  $("#sTotal").textContent = week.length.toLocaleString("vi-VN");
  $("#sSafe").textContent = safe.toLocaleString("vi-VN");
  $("#sWarned").textContent = warnedRows.length.toLocaleString("vi-VN");
  $("#sBlocked").textContent = blocked.toLocaleString("vi-VN");
  $("#sClosed").textContent = warnedRows.length ? `đóng ${closed.toLocaleString("vi-VN")}` : "—";
  $("#recentShort").innerHTML = rowsHTML(decisions.slice(0, 4));
  $("#recentFull").innerHTML = logging ? rowsHTML(decisions) : '<p class="empty">Nhật ký đang tắt.</p>';
}

async function refreshAll() {
  const settings = await refreshStatus();
  await refreshLog(settings.logDecisions);
}

// ---------- điều hướng ----------
/** @param {string} name */
function tab(name, refresh = true) {
  const tabs = $$("[data-tab]");
  if (!tabs.some((a) => a.dataset.tab === name)) name = "home";
  tabs.forEach((a, i) => {
    if (a.dataset.tab !== name) { a.removeAttribute("aria-current"); return; }
    a.setAttribute("aria-current", "page");
    $(".nav").style.setProperty("--i", String(i));
  });
  for (const p of $$("[data-pane]")) p.hidden = p.dataset.pane !== name;
  if (name === "check") window.setTimeout(() => $("#checkInput").focus(), 30);
  if (refresh && (name === "home" || name === "log")) refreshAll().catch((error) => toast(message(error), true));
}
for (const a of $$("[data-tab]")) {
  a.addEventListener("click", (event) => {
    event.preventDefault();
    history.replaceState(null, "", `#${a.dataset.tab}`);
    tab(a.dataset.tab ?? "home");
  });
}

// ---------- cài đặt: lưu ngay mỗi khi đổi ----------
/**
 * @param {Record<string, boolean | number>} changes
 * @returns {Promise<boolean>}
 */
async function save(changes) {
  try {
    await ask({ type: "settings", changes });
    toast("Đã lưu");
    return true;
  } catch (error) {
    toast(`Không lưu được cài đặt: ${message(error)}`, true);
    await refreshStatus().catch(() => undefined);   // trả giao diện về giá trị thật
    return false;
  }
}
for (const sw of $$(".switch[data-key]")) {
  sw.addEventListener("click", async () => {
    const on = sw.getAttribute("aria-checked") !== "true";
    sw.setAttribute("aria-checked", String(on));
    if (await save({ [sw.dataset.key ?? ""]: on }) && sw.dataset.key === "logDecisions") await refreshLog(on);
  });
}
for (const b of $$("#seconds button")) {
  b.addEventListener("click", async () => {
    for (const x of $$("#seconds button")) x.setAttribute("aria-pressed", String(x === b));
    await save({ frictionSeconds: Number(b.dataset.s) });
  });
}
for (const input of $$("input.num[data-key]")) {
  input.addEventListener("change", async () => {
    await save({ [input.dataset.key ?? ""]: Number(/** @type {HTMLInputElement} */ (input).value) });
  });
}

$("#updateNow").addEventListener("click", async (event) => {
  const button = /** @type {HTMLButtonElement} */ (event.currentTarget);
  button.disabled = true;
  button.textContent = "Đang thực hiện…";
  try {
    const outcome = await ask({ type: "update-now" });
    toast(outcome.log?.at(-1) ?? "Đã cập nhật");
    await refreshStatus();
  } catch (error) {
    toast(`Cập nhật lỗi: ${message(error)}`, true);
  } finally {
    button.disabled = false;
    button.textContent = "Cập nhật danh sách";
  }
});

$("#guardian-import").addEventListener("submit", async (event) => {
  event.preventDefault();
  const out = $("#guardian-import-status");
  const box = /** @type {HTMLTextAreaElement} */ ($("#guardian-policy"));
  try {
    const answer = await ask({ type: "guardian-import", text: box.value });
    out.textContent = answer.ok ? `Đã nhận chính sách phiên bản ${answer.version}.` : `Không nhận: ${answer.error}`;
    if (answer.ok) box.value = "";
    await refreshStatus();
  } catch (error) {
    out.textContent = `Không nhập được: ${message(error)}`;
  }
});

// ---------- kiểm tra link ----------
/**
 * @param {"ok" | "warn" | "high"} tone
 * @param {string} title
 * @param {string} sub
 * @param {number} score
 * @returns {string}
 */
function verdictHTML(tone, title, sub, score) {
  return `<div class="verdict verdict--${tone} in">${ICO[tone]}<div class="verdict-t">${esc(title)}<small>${esc(sub)}</small></div>`
    + `<div class="verdict-s" role="img" aria-label="${score}/100">${score}<small>/100</small></div></div>`;
}

/** @param {any} r Trả lời của thông điệp ``test``. */
function renderCheck(r) {
  const out = $("#checkResult");
  out.hidden = false;
  const domain = r.view.domain;
  if (r.level === "SAFE") {
    out.innerHTML = `${verdictHTML("ok", "An toàn", domain.registered, r.score)}`
      + `<div class="compare" style="margin-top:0;padding-top:0;border:0">${OK_ICON}<span>Không thấy dấu hiệu lừa đảo.</span></div>`;
    return;
  }
  const warn = r.level === "WARN";
  const parts = (domain.prefix ? `<span class="part ${domain.decoyPrefix ? "decoy" : "dim"}"><code>${esc(domain.prefix)}</code></span>` : "")
    + `<span class="part ${warn ? "warnpart" : "real"}"><code>${esc(domain.registered)}</code></span>`;
  const reasons = /** @type {{text: string}[]} */ (r.view.details).map((x) => `<li>${esc(x.text)}</li>`).join("");
  out.innerHTML = `${verdictHTML(warn ? "warn" : "high", warn ? "Đáng ngờ" : "Nguy hiểm", r.view.headline, r.score)}`
    + `<div class="parts">${parts}</div>`
    + (r.view.officialLine ? `<div class="compare">${OK_ICON}<span>${esc(r.view.officialLine)}</span></div>` : "")
    + (reasons ? `<ul>${reasons}</ul>` : "");
}

$("#checkForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = /** @type {HTMLInputElement} */ ($("#checkInput")).value.trim();
  if (!url) return;
  const out = $("#checkResult");
  const button = /** @type {HTMLButtonElement} */ ($("#checkBtn"));
  out.hidden = false;
  out.innerHTML = '<p class="busy">Đang kiểm tra…</p>';
  button.disabled = true;
  try {
    renderCheck(await ask({ type: "test", url }));
  } catch (error) {
    out.innerHTML = `<div class="top"><span class="chip warn">Không kiểm tra được</span> <b>${esc(message(error))}</b></div>`;
  } finally {
    button.disabled = false;
  }
});

// ---------- nhật ký: xóa (có hộp xác nhận tự vẽ) ----------
/** @returns {Promise<boolean>} */
function confirmClear() {
  const box = $("#sheet");
  const yes = $("#sheetYes");
  const no = $("#sheetNo");
  return new Promise((resolve) => {
    /** @param {boolean} value */
    const done = (value) => {
      box.removeAttribute("data-open");
      yes.onclick = no.onclick = box.onclick = null;
      document.removeEventListener("keydown", onKey);
      resolve(value);
    };
    /** @param {KeyboardEvent} e */
    const onKey = (e) => { if (e.key === "Escape") done(false); };
    yes.onclick = () => done(true);
    no.onclick = () => done(false);
    box.onclick = (e) => { if (e.target === box) done(false); };
    document.addEventListener("keydown", onKey);
    box.setAttribute("data-open", "");
    no.focus();
  });
}
$("#logClear").addEventListener("click", async () => {
  if (!(await confirmClear())) return;
  try {
    await ask({ type: "log-clear" });
    toast("Đã xóa nhật ký");
    await refreshLog(true);
  } catch (error) {
    toast(`Không xóa được: ${message(error)}`, true);
  }
});

tab(location.hash.slice(1), false);
window.addEventListener("hashchange", () => tab(location.hash.slice(1)));
refreshAll().catch((error) => toast(`Không nạp được trạng thái: ${message(error)}`, true));

// ---------- kéo khung điện thoại đi quanh trang: giữ thanh trên cùng rồi kéo; nhấp đúp để về giữa ----------
(() => {
  const shell = $(".shell");
  const bar = $(".tb");
  const KEEP = 60;                                           // luôn chừa ít nhất ngần này điểm ảnh của khung trong màn hình
  const fullscreen = window.matchMedia("(max-width: 440px), (max-height: 520px)");
  const pos = { x: 0, y: 0 };
  /** @type {{px: number, py: number, x: number, y: number} | null} */
  let drag = null;

  /**
   * @param {number} x
   * @param {number} y
   */
  function place(x, y) {
    if (fullscreen.matches) { pos.x = pos.y = 0; shell.style.transform = ""; return; }
    const r = shell.getBoundingClientRect();
    const baseX = r.left - pos.x;
    const baseY = r.top - pos.y;
    pos.x = Math.min(Math.max(x, KEEP - r.width - baseX), window.innerWidth - KEEP - baseX);
    pos.y = Math.min(Math.max(y, -baseY), window.innerHeight - bar.offsetHeight - baseY);
    shell.style.transform = pos.x || pos.y ? `translate(${Math.round(pos.x)}px, ${Math.round(pos.y)}px)` : "";
  }
  function save() {
    try { localStorage.setItem("chottoShellPos", JSON.stringify(pos)); } catch { /* chế độ riêng tư: bỏ qua */ }
  }

  bar.title = "Giữ và kéo để di chuyển, nhấp đúp để về giữa";
  bar.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || fullscreen.matches) return;
    bar.setPointerCapture(event.pointerId);
    drag = { px: event.clientX, py: event.clientY, x: pos.x, y: pos.y };
    shell.classList.add("dragging");
  });
  bar.addEventListener("pointermove", (event) => {
    if (drag) place(drag.x + event.clientX - drag.px, drag.y + event.clientY - drag.py);
  });
  const end = () => {
    if (!drag) return;
    drag = null;
    shell.classList.remove("dragging");
    save();
  };
  bar.addEventListener("pointerup", end);
  bar.addEventListener("pointercancel", end);
  bar.addEventListener("dblclick", () => { place(0, 0); save(); });
  window.addEventListener("resize", () => place(pos.x, pos.y));

  try {
    const saved = JSON.parse(localStorage.getItem("chottoShellPos") ?? "null");
    if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) place(saved.x, saved.y);
  } catch { /* chưa có vị trí đã lưu */ }
})();
