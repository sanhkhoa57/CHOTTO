// Cửa sổ ứng dụng (Tổng quan, Kiểm tra link, Nhật ký, Cài đặt). Cầu nối Python: chotto/webhost.AppApi.
//   api.state()  api.save(values)  api.check(url)  api.action(name)  api.window(op)  api.mascot()
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
    buddyRows();
    if (state) renderState(state);
    lastCheck = null;                                    // kết quả cũ viết bằng ngôn ngữ trước: kiểm tra lại
    $("#checkResult").hidden = true;
  }

  const ICO = {
    ok: '<svg viewBox="0 0 24 24"><path d="M12 3l8 3v6c0 4.5-3.3 8-8 9-4.7-1-8-4.5-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/></svg>',
    warn: '<svg viewBox="0 0 24 24"><path d="M12 3.5 22 20.5H2z"/><path d="M12 10v4.5M12 17.4h.01"/></svg>',
    high: '<svg viewBox="0 0 24 24"><path d="M8.2 3h7.6L21 8.2v7.6L15.8 21H8.2L3 15.8V8.2z"/><path d="M12 7.5v5.5M12 16.5h.01"/></svg>',
  };
  // Tem tròn có viền lượn sóng (như nhãn "Get your mental health in order" ở ảnh mẫu).
  const BURST = (() => {
    let d = "";
    for (let i = 0; i <= 120; i++) {
      const a = (i / 120) * Math.PI * 2, r = 45 + 3.6 * Math.cos(a * 12);
      d += `${i ? "L" : "M"}${(50 + r * Math.cos(a)).toFixed(1)} ${(50 + r * Math.sin(a)).toFixed(1)}`;
    }
    return `<svg viewBox="0 0 100 100"><path class="burst" d="${d}Z"/></svg>`;
  })();
  const GLYPH = {
    ok: '<svg class="glyph" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    warn: '<svg class="glyph" viewBox="0 0 24 24"><path d="M12 5v9M12 18.5h.01"/></svg>',
  };
  const verdictHTML = (tone, title, sub, score) => `<div class="verdict verdict--${tone} in">${ICO[tone === "ok" ? "ok" : tone]}`
    + `<div class="verdict-t">${esc(title)}<small>${esc(sub)}</small></div>`
    + `<div class="verdict-s" role="img" aria-label="${score}/100">${score}<small>/100</small></div></div>`;

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
    $("#guardIco").innerHTML = BURST + (protectedNow ? GLYPH.ok : GLYPH.warn);
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
    buddySync(s);
    buddyPlaceUI();
  }
  async function refresh() {
    if (!api) return;
    const s = await api.state();
    if (s.settings.ui_language !== I18N.lang) { state = s; applyLanguage(s.settings.ui_language); }
    else renderState(s);
  }

  // ---------- điều hướng ----------
  function tab(name) {
    $$("[data-tab]").forEach((a, i) => {
      if (a.dataset.tab !== name) return a.removeAttribute("aria-current");
      a.setAttribute("aria-current", "page");
      a.closest(".nav").style.setProperty("--i", i);          // viên cam trượt tới tab này
    });
    $$("[data-pane]").forEach((p) => (p.hidden = p.dataset.pane !== name));
    if (name === "check") setTimeout(() => $("#checkInput").focus(), 30);
    if (name === "home" || name === "log") refresh();
    if (name === "settings") buddyLoad();
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
    buddyPlaceUI();
    save({ [k]: k === "unknown_caller_policy" ? (on ? "inspect" : "forward") : on }, () => { sw.setAttribute("aria-checked", !on); buddyPlaceUI(); });
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

  // ---------- nhân vật taskbar: xem trước + tô màu (chotto/web/mascot.js), lưu vào mascot_colors ----------
  // Agent nhận tín hiệu config_changed nên nhân vật trên taskbar đổi màu/ẩn hiện ngay, không cần khởi động lại.
  const BUDDY = { P: null, px: [], cvs: [], cur: null, timer: 0, loading: false };
  const validColors = (c) => Array.isArray(c) && c.length === 6 && c.every((x) => /^#[0-9a-f]{6}$/i.test(x));
  function buddyRender() {
    if (!BUDDY.P || !BUDDY.cur) return;
    BUDDY.px.forEach((p, n) => {
      const cv = BUDDY.cvs[n], ctx = cv.getContext("2d"), out = ctx.createImageData(p.w, p.h);
      window.CHOTTO_MASCOT.recolor(p.a.data, p.m.data, out.data, BUDDY.cur, BUDDY.P);
      ctx.putImageData(out, 0, 0);
    });
  }
  function buddyMark() {
    if (!BUDDY.cur) return;
    $$("#buddyRows .buddy-sw").forEach((w) => {
      const c = BUDDY.cur[Number(w.dataset.g)].toLowerCase();
      let hit = false;
      $$("button", w).forEach((b) => { const on = b.dataset.c === c; hit = hit || on; b.setAttribute("aria-pressed", on); });
      const lab = $("label", w);
      lab.classList.toggle("on", !hit);
      $("input", w).value = c;
      if (!hit) lab.style.background = c; else lab.style.removeProperty("background");
    });
  }
  function buddyRows() {
    const box = $("#buddyRows");
    if (!BUDDY.P) { box.innerHTML = ""; return; }
    box.innerHTML = BUDDY.P.default.map((def, g) => {
      const name = esc(t(`buddy.g${g}`));
      const sw = [def].concat(BUDDY.P.swatches[g]).map((c, i) =>
        `<button style="background:${esc(c)}" data-c="${esc(c.toLowerCase())}" aria-pressed="false" title="${i ? esc(c) : esc(t("buddy.default"))}"
          aria-label="${name}: ${i ? esc(c) : esc(t("buddy.default"))}"></button>`).join("");
      return `<div class="buddy-row"><span>${name}</span><div class="buddy-sw" data-g="${g}">${sw}`
        + `<label title="${esc(t("buddy.pick"))}"><input type="color" aria-label="${name}: ${esc(t("buddy.pick"))}"></label></div></div>`;
    }).join("");
    $$("#buddyRows .buddy-sw").forEach((w) => {
      const g = Number(w.dataset.g);
      $$("button", w).forEach((b) => b.addEventListener("click", () => buddySet(g, b.dataset.c)));
      $("input", w).addEventListener("input", (e) => buddySet(g, e.target.value.toLowerCase()));
    });
    $$("#buddyStage figcaption").forEach((f, n) => { f.textContent = t(`buddy.p${n}`); });
    buddyMark();
  }
  function buddySave() {
    clearTimeout(BUDDY.timer);
    BUDDY.timer = setTimeout(() => {
      BUDDY.timer = 0;
      const before = state && state.settings.mascot_colors;
      save({ mascot_colors: BUDDY.cur.slice() }, () => { if (validColors(before)) { BUDDY.cur = before.slice(); buddyRender(); buddyMark(); } });
    }, 350);
  }
  function buddySet(g, c) {
    if (!BUDDY.cur) return;
    BUDDY.cur[g] = c;
    buddyRender(); buddyMark(); buddySave();
  }
  function buddySync(s) {
    $("#buddyNote").hidden = s.mascot_supported !== false;
    if (BUDDY.timer) return;                                 // đang chờ lưu: giữ màu người dùng vừa chọn
    const colors = validColors(s.settings.mascot_colors) ? s.settings.mascot_colors : (BUDDY.P && BUDDY.P.default);
    if (!colors) return;
    BUDDY.cur = colors.map((c) => c.toLowerCase());
    buddyRender(); buddyMark();
  }
  const loadImg = (src) => new Promise((ok, fail) => { const i = new Image(); i.onload = () => ok(i); i.onerror = fail; i.src = src; });
  function pixels(img) {
    const c = document.createElement("canvas");
    c.width = img.width; c.height = img.height;
    const x = c.getContext("2d");
    x.drawImage(img, 0, 0);
    return x.getImageData(0, 0, img.width, img.height);
  }
  async function buddyLoad() {
    if (BUDDY.P || BUDDY.loading) return;
    BUDDY.loading = true;
    try {
      let data;
      if (api && api.mascot) data = await api.mascot();
      else {                                                 // ?demo: đọc thẳng file (cần máy chủ http cục bộ để đọc được điểm ảnh)
        const palette = await (await fetch("../mascot/assets/palette.json")).json();
        data = { ok: true, palette, poses: [0, 1, 2, 3].map((n) => ({ img: `../mascot/assets/pose_${n}.png`, mask: `../mascot/assets/mask_${n}.png` })) };
      }
      if (!data || !data.ok) throw new Error("no assets");
      const pairs = await Promise.all(data.poses.map((p) => Promise.all([loadImg(p.img), loadImg(p.mask)])));
      const stage = $("#buddyStage");
      stage.innerHTML = "";
      BUDDY.px = pairs.map(([img, mask]) => ({ a: pixels(img), m: pixels(mask), w: img.width, h: img.height }));
      BUDDY.cvs = pairs.map(([img], n) => {
        const fig = document.createElement("figure"), cv = document.createElement("canvas");
        cv.width = img.width; cv.height = img.height;
        cv.setAttribute("aria-hidden", "true");
        fig.append(cv, document.createElement("figcaption"));
        stage.append(fig);
        return cv;
      });
      BUDDY.P = data.palette;
      if (state) state.mascot_supported = data.supported !== false;
      buddyRows();
      if (state) buddySync(state);
    } catch (err) {
      $("#buddyStage").hidden = true;                        // không có asset: vẫn bật/tắt được, chỉ thiếu phần xem trước
    } finally {
      BUDDY.loading = false;
    }
  }
  function buddyRandom() {
    if (!BUDDY.P) return;
    BUDDY.cur = BUDDY.P.default.map((def, g) => { const l = [def].concat(BUDDY.P.swatches[g]); return l[Math.floor(Math.random() * l.length)]; });
    buddyRender(); buddyMark(); buddySave();
  }
  function buddyReset() {
    if (!BUDDY.P) return;
    BUDDY.cur = BUDDY.P.default.slice();
    buddyRender(); buddyMark(); buddySave();
  }
  // "Chọn vị trí": agent cho kéo nhân vật bằng chuột; chỉ dùng được khi nhân vật đang hiện và đã bật "cố định".
  let placing = false;
  const switchOn = (key) => { const sw = $(`.switch[data-key="${key}"]`); return !!sw && sw.getAttribute("aria-checked") === "true"; };
  function buddyPlaceUI() {
    const ok = switchOn("mascot_enabled") && switchOn("mascot_pinned") && (!state || state.mascot_supported !== false);
    if (!ok && placing) { placing = false; if (api && api.mascot_place) api.mascot_place(false); }
    const open = switchOn("mascot_enabled") && (!state || state.mascot_supported !== false);
    const fold = $("#buddyFold");
    fold.dataset.open = open;
    fold.inert = !open;                      // thu lại thì không focus/bấm được các nút bên trong
    const btn = $("#buddyPlace");
    btn.disabled = !ok;
    btn.setAttribute("aria-pressed", placing);
    btn.textContent = t(placing ? "buddy.placeDone" : "buddy.placeBtn");
    $("#buddyPlaceHint").classList.toggle("on", placing);
  }
  $("#buddyPlace").addEventListener("click", () => {
    placing = !placing;
    if (api && api.mascot_place) api.mascot_place(placing);
    buddyPlaceUI();
  });
  $("#buddyRandom").addEventListener("click", buddyRandom);
  $("#buddyReset").addEventListener("click", buddyReset);

  // Hộp xác nhận tự vẽ: mặc định focus vào "Giữ lại"; Esc hoặc bấm ra ngoài = hủy.
  function ask(kind = "confirm") {
    const box = $("#sheet"), yes = $("#sheetYes"), no = $("#sheetNo");
    $("#sheetT").textContent = t(`${kind}.title`);
    $("#sheetP").textContent = t(`${kind}.body`);
    yes.textContent = t(`${kind}.yes`);
    return new Promise((resolve) => {
      const done = (value) => {
        box.removeAttribute("data-open");
        document.removeEventListener("keydown", onKey, true);
        resolve(value);
      };
      const onKey = (e) => { if (e.key === "Escape") { e.preventDefault(); done(false); } };
      yes.onclick = () => done(true);
      no.onclick = () => done(false);
      box.onclick = (e) => { if (e.target === box) done(false); };
      document.addEventListener("keydown", onKey, true);
      box.setAttribute("data-open", "");
      no.focus();
    });
  }
  // ---------- tác vụ ----------
  async function runAction(name, button) {
    if (!api) return;
    if (name === "uninstall" && !(await ask("confirm"))) return;
    if (name === "clear_log" && !(await ask("clear"))) return;
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
      out.innerHTML = `${verdictHTML("ok", t("check.safe"), r.domain, r.score)}
        <div class="compare" style="margin-top:0;padding-top:0;border:0">${okIcon}<span>${esc(t("check.safeText"))}</span></div>`;
    } else {
      const v = r.view;
      const warn = v.level === "WARN";
      out.innerHTML = `${verdictHTML(warn ? "warn" : "high", t(warn ? "check.suspicious" : "check.danger"), v.title, v.score)}
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
    default_handler: !location.search.includes("off"), blacklist_text: "Scam list updated at 07:42 today",
    settings: { tier3_enabled: true, ai_advice: true, log_decisions: true, unknown_caller_policy: "inspect", friction_seconds: 5,
      ui_language: location.search.includes("vi") ? "vi" : "en",
      mascot_enabled: true, mascot_pinned: false, mascot_colors: ["#3c3840", "#503065", "#f8d5c0", "#342928", "#25242b", "#bc8e3f"] },
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
