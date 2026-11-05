// Màn hình đệm. Dữ liệu đến từ Python (chotto/webhost.py) qua pywebview:
//   api.initial()        -> {view, lock_s}   (view: chotto/viewmodel.friction_view, có view.lang)
//   api.decide(proceed)  -> {ok}             (Python tự kiểm lại thời gian khóa)
//   window.CHOTTO.update({view, lock_s})     do Python gọi khi Tầng 3 xong
// Mở bằng trình duyệt thường với ?demo để xem với dữ liệu mẫu (?demo&vi để xem tiếng Việt).
"use strict";
(() => {
  const $ = (s) => document.querySelector(s);
  const I18N = window.CHOTTO_I18N;
  const t = I18N.t;
  const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const okIcon = '<span class="ok" aria-hidden="true"><svg viewBox="0 0 16 16"><path d="m3.5 8.4 2.8 2.8 6.2-6.4"/></svg></span>';
  const RING = 50.27;

  let api = null;
  let opened = 0;          // thời điểm hiện cửa sổ (performance.now)
  let unlockAt = Infinity;
  let shownLevel = "";
  let deciding = false;

  function setMeter(score) {
    const spans = document.querySelectorAll(".track i");
    [[0, 30], [30, 60], [60, 100]].forEach(([a, b], i) => {
      spans[i].style.transform = `scaleX(${Math.max(0, Math.min(1, (score - a) / (b - a)))})`;
    });
  }

  function render(view, fresh) {
    if (view.lang && view.lang !== I18N.lang) I18N.apply(view.lang);
    const level = view.level;
    $("#shell").dataset.level = level;
    $("#verdict").dataset.level = level;
    $("#vTitle").textContent = view.title;
    $("#vText").textContent = view.text;
    $("#vScore").textContent = view.score;
    setMeter(view.score);
    $("#parts").innerHTML = view.parts.map((p) =>
      `<span class="part ${esc(p.kind)}"><code>${esc(p.text)}</code>${p.label ? `<small>${esc(p.label)}</small>` : ""}</span>`).join("");
    const compare = $("#compare");
    compare.hidden = !view.official;
    if (view.official) compare.innerHTML = `${okIcon}<span>${t("official", { brand: esc(view.brand), domain: esc(view.official) })}</span>`;
    $("#full").textContent = view.full_url;
    $("#reasonsTitle").textContent = t(level === "WARN" ? "f.whyWarn" : "f.whyBlock");
    const rows = view.reasons.map((r) => `<li><i class="dot"></i><div>${esc(r)}</div></li>`);
    if (view.checking) rows.push(`<li><i class="dot pending"></i><div>${esc(t("f.checking"))}</div></li>`);
    $("#reasons").innerHTML = rows.join("");
    if (fresh) $("#reasons").lastElementChild?.classList.add("fresh");
    $("#src").textContent = t("f.source", { s: view.source });
    $("#adviceText").textContent = view.advice || view.general;
    $("#general").textContent = view.advice ? t("f.call") : "";
    shownLevel = level;
  }

  function setLock(seconds) {
    unlockAt = Math.max(unlockAt === Infinity ? 0 : unlockAt, opened + seconds * 1000);
  }

  function tick() {
    const btn = $("#btnOpen");
    const left = unlockAt - performance.now();
    const total = unlockAt - opened;
    $("#ring").style.strokeDashoffset = RING * Math.max(0, left / total);
    if (left > 0) {
      btn.disabled = true;
      $("#openLabel").textContent = t("f.openIn", { n: Math.ceil(left / 1000) });
    } else if (btn.disabled) {
      btn.disabled = false;
      $("#openLabel").textContent = t("f.open");
    }
    requestAnimationFrame(tick);
  }

  async function decide(proceed) {
    if (deciding) return;
    if (proceed && performance.now() < unlockAt) return;
    deciding = true;
    try {
      const reply = api ? await api.decide(proceed) : { ok: true };
      if (!reply || !reply.ok) deciding = false;     // Python từ chối (còn khóa): cho bấm lại sau
    } catch (err) {
      deciding = false;
    }
  }

  window.CHOTTO = {
    update(payload) {
      const rising = payload.view.level !== shownLevel;
      render(payload.view, true);
      if (rising) setLock(payload.lock_s);
    },
  };

  function start(payload) {
    opened = performance.now();
    render(payload.view, false);
    setLock(payload.lock_s);
    requestAnimationFrame(tick);
    $("#btnClose").focus();
  }

  $("#btnClose").addEventListener("click", () => decide(false));
  $("#btnX").addEventListener("click", () => decide(false));
  $("#btnOpen").addEventListener("click", () => decide(true));
  $("#btnMin").addEventListener("click", () => api && api.minimize());
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") decide(false); });

  const DEMO = {
    en: {
      lock_s: 8,
      view: {
        lang: "en", level: "HIGH", score: 92, title: "This is a fake page.", text: "Don't sign in or enter any OTP code on this page.",
        parts: [{ text: "https://", kind: "dim", label: "" }, { text: "vietcombank.com.vn.", kind: "decoy", label: "disguise" },
          { text: "xacthuc-tk.top", kind: "real", label: "where you actually go" }, { text: "/dang-nhap", kind: "dim", label: "" }],
        brand: "Vietcombank", official: "vietcombank.com.vn",
        reasons: ["This domain is on a scam list reported by the community", "The domain contains the name “Vietcombank” but is not the official site", "Domain registered only 2 day(s) ago"],
        checking: false,
        advice: "A fake Vietcombank page on a domain registered a few days ago: almost certainly a scam. Never sign in or enter an OTP code.",
        general: "", source: "Scam list", full_url: "https://vietcombank.com.vn.xacthuc-tk.top/dang-nhap?ref=zalo",
      },
    },
    vi: {
      lock_s: 8,
      view: {
        lang: "vi", level: "HIGH", score: 92, title: "Đây là trang giả.", text: "Đừng đăng nhập hay nhập mã OTP vào trang này.",
        parts: [{ text: "https://", kind: "dim", label: "" }, { text: "vietcombank.com.vn.", kind: "decoy", label: "phần ngụy trang" },
          { text: "xacthuc-tk.top", kind: "real", label: "nơi bạn thật sự tới" }, { text: "/dang-nhap", kind: "dim", label: "" }],
        brand: "Vietcombank", official: "vietcombank.com.vn",
        reasons: ["Tên miền nằm trong danh sách lừa đảo đã được cộng đồng báo cáo", "Tên miền chứa tên “Vietcombank” nhưng không phải trang chính thức", "Tên miền mới đăng ký cách đây 2 ngày"],
        checking: false,
        advice: "Trang giả Vietcombank trên một tên miền vừa đăng ký vài ngày: gần như chắc chắn là lừa đảo. Tuyệt đối không đăng nhập hay nhập mã OTP.",
        general: "", source: "Danh sách lừa đảo", full_url: "https://vietcombank.com.vn.xacthuc-tk.top/dang-nhap?ref=zalo",
      },
    },
  };

  function boot() {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.initial) {
      api = window.pywebview.api;
      api.initial().then(start);
    } else if (location.search.includes("demo")) {
      start(location.search.includes("vi") ? DEMO.vi : DEMO.en);
    }
  }
  I18N.apply("en");
  if (window.pywebview && window.pywebview.api) boot();
  else window.addEventListener("pywebviewready", boot);
  if (location.search.includes("demo")) window.addEventListener("DOMContentLoaded", boot);
})();
