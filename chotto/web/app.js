// Cửa sổ ứng dụng (Tổng quan, Kiểm tra link, Nhật ký, Cài đặt). Cầu nối Python: chotto/webhost.AppApi.
//   api.state()  api.save(values)  api.check(url)  api.action(name)  api.window(op)
// Ngôn ngữ: settings.ui_language ("en" mặc định | "vi"), chữ lấy từ i18n.js.
// Mở bằng trình duyệt thường với ?demo để xem với dữ liệu mẫu (?demo&vi để xem tiếng Việt).
"use strict";
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const I18N = window.CHOTTO_I18N;
  const t = I18N.t;
  const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const okIcon = '<span class="ok" aria-hidden="true"><svg viewBox="0 0 16 16"><path d="m3.5 8.4 2.8 2.8 6.2-6.4"/></svg></span>';
  let api = null;
  let state = null;
  let lastCheck = null;

  // ---------- tiện ích ----------
  let toastTimer = 0;
  function toast(text, isError) {
    const el = $("#toast");
    el.textContent = text;
    el.classList.toggle("err", !!isError);
    el.classList.add("on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("on"), isError ? 5000 : 2200);
  }
  const fmt = (n) => Number(n).toLocaleString(I18N.locale());
  function when(ts) {
    const d = new Date(ts * 1000), now = new Date();
    const hm = d.toLocaleTimeString(I18N.locale(), { hour: "2-digit", minute: "2-digit" });
    const days = Math.round((new Date(now.toDateString()) - new Date(d.toDateString())) / 86400000);
    if (days === 0) return t("today", { t: hm });
    if (days === 1) return t("yesterday", { t: hm });
    return `${d.toLocaleDateString(I18N.locale(), { day: "2-digit", month: "2-digit" })}, ${hm}`;
  }
  const TONE = { auto_open: "ok", ui_failed_blocked: "high", ui_failed_open: "warn" };
  function chip(row) {
    const label = t(`dec.${row.decision}`);
    const tone = TONE[row.decision] || (row.level === "WARN" ? "warn" : row.level === "SAFE" ? "ok" : "high");
    return `<span class="chip ${tone}">${esc(label)}</span>`;
  }
  function rowsHTML(rows) {
    if (!rows.length) return `<p class="empty">${esc(t("recent.empty"))}</p>`;
    return rows.map((r) => `<div class="row"><span class="d">${esc(r.host)}</span><span class="t">${esc(when(r.ts))}</span>${chip(r)}</div>`).join("");
  }
  const partsHTML = (parts) => parts.map((p) =>
    `<span class="part ${esc(p.kind)}"><code>${esc(p.text)}</code>${p.label ? `<small>${esc(p.label)}</small>` : ""}</span>`).join("");
  const officialHTML = (v) => (v.official
    ? `<div class="compare">${okIcon}<span>${t("official", { brand: esc(v.brand), domain: esc(v.official) })}</span></div>` : "");

  // ---------- ngôn ngữ ----------
  function applyLanguage(lang) {
    I18N.apply(lang);
    $("#credit").innerHTML = esc(t("footer")).replace("AECCUS", "<b>AECCUS</b>");
    $$("[data-lang-switch] button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.lang === I18N.lang));
    $$("#seconds button").forEach((b) => { b.textContent = t("sec", { n: b.dataset.s }); });
    if (state) renderState(state);
    lastCheck = null;                                    // kết quả cũ viết bằng ngôn ngữ trước: kiểm tra lại
    $("#checkResult").hidden = true;
  }

  // ---------- hiển thị trạng thái ----------
  function renderState(s) {
    state = s;
    const sum = s.summary;
    $("#sTotal").textContent = fmt(sum.total);
    $("#sSafe").textContent = fmt(sum.safe);
    $("#sWarned").textContent = fmt(sum.warned);
    $("#sBlocked").textContent = fmt(sum.blocked);
    $("#sClosed").textContent = sum.warned ? t("tile.closed", { n: fmt(sum.closed) }) : t("tile.none");
    const protectedNow = s.default_handler !== false;
    $("#guard").classList.toggle("off", !protectedNow);
    $("#guardTitle").textContent = t(protectedNow ? "guard.on" : "guard.off");
    $("#guardText").textContent = protectedNow ? s.blacklist_text : t("guard.offText");
    $("#guardInstall").hidden = protectedNow;
    // Đã là trình mở link mặc định: báo thành công (giống bản Android) thay cho nút cài.
    $("#guardBadge").hidden = s.default_handler !== true;
    const setInstall = $("#setInstall");
    setInstall.textContent = t(s.default_handler === true ? "act.installed" : "act.install");
    setInstall.disabled = s.default_handler === true;
    $("#recentShort").innerHTML = rowsHTML(s.recent.slice(0, 4));
    $("#recentFull").innerHTML = s.settings.log_decisions ? rowsHTML(s.recent) : `<p class="empty">${esc(t("log.off"))}</p>`;
    $$(".switch[data-key]").forEach((sw) => {
      const k = sw.dataset.key;
      sw.setAttribute("aria-checked", k === "unknown_caller_policy" ? s.settings[k] === "inspect" : !!s.settings[k]);
    });
    $$("#seconds button").forEach((b) => b.setAttribute("aria-pressed", Number(b.dataset.s) === s.settings.friction_seconds));
  }
  async function refresh() {
    if (!api) return;
    const s = await api.state();
    if (s.settings.ui_language !== I18N.lang) { state = s; applyLanguage(s.settings.ui_language); }
    else renderState(s);
  }

  // ---------- điều hướng ----------
  function tab(name) {
    $$("[data-tab]").forEach((a) => (a.dataset.tab === name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    $$("[data-pane]").forEach((p) => (p.hidden = p.dataset.pane !== name));
    if (name === "check") setTimeout(() => $("#checkInput").focus(), 30);
    if (name === "home" || name === "log") refresh();
  }
  $$("[data-tab]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); tab(a.dataset.tab); }));
  $$("[data-win]").forEach((b) => b.addEventListener("click", () => api && api.window(b.dataset.win)));

  // Cửa sổ không viền: tự vẽ mép kéo giãn (độ dời tính bằng điểm ảnh vật lý, gộp theo khung hình).
  $$(".rz").forEach((grip) => {
    grip.addEventListener("pointerdown", (e) => {
      if (!api || e.button !== 0) return;
      e.preventDefault();
      grip.setPointerCapture(e.pointerId);
      const x0 = e.screenX, y0 = e.screenY, dpr = window.devicePixelRatio || 1;
      let pending = null, queued = false;
      api.resize_begin(grip.dataset.edge);
      const flush = () => { queued = false; if (pending) { api.resize_move(pending[0], pending[1]); pending = null; } };
      const move = (ev) => {
        pending = [(ev.screenX - x0) * dpr, (ev.screenY - y0) * dpr];
        if (!queued) { queued = true; requestAnimationFrame(flush); }
      };
      const end = () => {
        grip.removeEventListener("pointermove", move);
        grip.removeEventListener("pointerup", end);
        grip.removeEventListener("pointercancel", end);
      };
      grip.addEventListener("pointermove", move);
      grip.addEventListener("pointerup", end);
      grip.addEventListener("pointercancel", end);
    });
  });

  // ---------- cài đặt: lưu ngay ----------
  async function save(patch, revert) {
    if (!api) return true;
    try {
      const reply = await api.save(patch);
      if (reply.ok) { if (state) state.settings = reply.settings; toast(t("saved")); return true; }
      revert(); toast(reply.error || t("saveFail"), true);
    } catch (err) {
      revert(); toast(t("saveFail"), true);
    }
    return false;
  }
  $$(".switch[data-key]").forEach((sw) => sw.addEventListener("click", () => {
    const on = sw.getAttribute("aria-checked") !== "true";
    sw.setAttribute("aria-checked", on);
    const k = sw.dataset.key;
    save({ [k]: k === "unknown_caller_policy" ? (on ? "inspect" : "forward") : on }, () => sw.setAttribute("aria-checked", !on));
  }));
  $$("#seconds button").forEach((b) => b.addEventListener("click", () => {
    const before = $("#seconds [aria-pressed=true]");
    $$("#seconds button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    save({ friction_seconds: Number(b.dataset.s) }, () => $$("#seconds button").forEach((x) => x.setAttribute("aria-pressed", x === before)));
  }));
  $$("[data-lang-switch] button").forEach((b) => b.addEventListener("click", () => {
    const before = I18N.lang;
    if (b.dataset.lang === before) return;
    applyLanguage(b.dataset.lang);                       // đổi ngay, không chờ Python
    save({ ui_language: b.dataset.lang }, () => applyLanguage(before));
  }));

  // ---------- tác vụ ----------
  async function runAction(name, button) {
    if (!api) return;
    if (name === "uninstall" && !confirm(t("confirm.uninstall"))) return;
    const label = button ? button.textContent : "";
    if (button) { button.disabled = true; button.textContent = t("act.busy"); }
    try {
      const reply = await api.action(name);
      if (reply.message) toast(reply.message, !reply.ok);
    } finally {
      if (button) { button.disabled = false; button.textContent = label; }
      refresh();
    }
  }
  $$("[data-action]").forEach((b) => b.addEventListener("click", () => runAction(b.dataset.action, b)));
  $("#guardInstall").addEventListener("click", (e) => runAction("install", e.currentTarget));

  // ---------- kiểm tra link ----------
  function renderCheck(r) {
    const out = $("#checkResult");
    out.hidden = false;
    if (!r.ok) {
      out.innerHTML = `<div class="top"><span class="chip warn">${esc(t("check.fail"))}</span><b>${esc(r.error || t("check.error"))}</b></div>`;
    } else if (r.level === "SAFE") {
      out.innerHTML = `<div class="top"><span class="chip ok">${esc(t("check.safe"))}</span><b>${esc(r.domain)}</b><span class="sc">${r.score}/100</span></div>
        <div class="compare" style="margin-top:0;padding-top:0;border:0">${okIcon}<span>${esc(t("check.safeText"))}</span></div>`;
    } else {
      const v = r.view;
      const warn = v.level === "WARN";
      out.innerHTML = `<div class="top"><span class="chip ${warn ? "warn" : "high"}">${esc(t(warn ? "check.suspicious" : "check.danger"))}</span><b>${esc(v.title)}</b><span class="sc">${v.score}/100</span></div>
        <div class="parts">${partsHTML(v.parts)}</div>${officialHTML(v)}
        ${v.reasons.length ? `<ul>${v.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}`;
    }
  }
  $("#checkForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = $("#checkInput").value.trim();
    if (!url || !api) return;
    const out = $("#checkResult");
    out.hidden = false;
    out.innerHTML = `<p class="busy">${esc(t("check.busy"))}</p>`;
    $("#checkBtn").disabled = true;
    try {
      lastCheck = await api.check(url);
    } catch (err) {
      lastCheck = { ok: false, error: t("check.error") };
    } finally {
      $("#checkBtn").disabled = false;
    }
    renderCheck(lastCheck);
  });

  // ---------- khởi động ----------
  const now = Date.now() / 1000;
  const DEMO = {
    default_handler: true, blacklist_text: "Scam list updated at 07:42 today",
    settings: { tier3_enabled: true, ai_advice: true, log_decisions: true, unknown_caller_policy: "inspect", friction_seconds: 5,
      ui_language: location.search.includes("vi") ? "vi" : "en" },
    summary: { total: 128, safe: 121, warned: 7, closed: 6, blocked: 2 },
    recent: [
      { ts: now - 3600, host: "xacthuc-tk.top", level: "BLOCKED", decision: "cancel" },
      { ts: now - 90000, host: "shopee-khuyenmai247.com", level: "HIGH", decision: "cancel" },
      { ts: now - 95000, host: "vnexpress.net", level: "SAFE", decision: "auto_open" },
      { ts: now - 200000, host: "bit.ly", level: "WARN", decision: "proceed" },
    ],
  };
  function boot() {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.state) {
      api = window.pywebview.api;
      refresh();
    } else if (location.search.includes("demo")) {
      state = DEMO;
      applyLanguage(DEMO.settings.ui_language);
    }
    const start = (location.hash || "").slice(1);
    if (["home", "check", "log", "settings"].includes(start)) tab(start);
  }
  applyLanguage("en");
  window.CHOTTO = { refresh, tab };
  if (window.pywebview && window.pywebview.api) boot();
  else window.addEventListener("pywebviewready", boot);
  if (location.search.includes("demo")) window.addEventListener("DOMContentLoaded", boot);
  window.addEventListener("focus", refresh);
})();
