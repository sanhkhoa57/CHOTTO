// Màn hình đệm. Dữ liệu đến từ Python (chotto/webhost.py) qua pywebview:
//   api.initial()        -> {view, lock_s}   (view: chotto/shield.shield_view, có view.lang)
//   api.decide(proceed)  -> {ok}             (Python tự kiểm lại thời gian khóa)
//   window.CHOTTO.update({view, lock_s})     do Python gọi khi Tầng 3 xong (mức chỉ tăng, bố cục không nhảy)
// Phần dựng giao diện nằm ở shield.js (dùng chung với tiện ích trình duyệt). Mở bằng trình duyệt thường với ?demo
// để xem với dữ liệu mẫu (?demo&vi: tiếng Việt; ?demo&level=WARN|HIGH|BLOCKED; ?demo&checking: đang tra tuổi tên miền).
"use strict";
(() => {
  const I18N = window.CHOTTO_I18N;

  let api = null;
  let shield = null;
  let opened = 0;          // thời điểm hiện cửa sổ (performance.now)
  let unlockAt = Infinity;
  let shownLevel = "";
  let deciding = false;

  function setLock(seconds) {
    unlockAt = Math.max(unlockAt === Infinity ? 0 : unlockAt, opened + seconds * 1000);
  }

  function tick() {
    const left = unlockAt - performance.now();
    shield.setLock(Math.max(0, Math.ceil(left / 1000)), left / Math.max(1, unlockAt - opened));
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

  function show(view) {
    if (view.lang && view.lang !== I18N.lang) I18N.apply(view.lang);
    document.documentElement.lang = view.lang || "en";
    if (shield) shield.update(view);
    else {
      shield = window.ChottoShield.mount(document.getElementById("scroll"), view, { theme: "light" });
      shield.back.addEventListener("click", () => decide(false));
      shield.proceed.addEventListener("click", () => decide(true));
    }
    shownLevel = view.level;
  }

  window.CHOTTO = {
    update(payload) {
      const rising = payload.view.level !== shownLevel;
      show(payload.view);
      if (rising) setLock(payload.lock_s);
    },
  };

  function start(payload) {
    opened = performance.now();
    show(payload.view);
    setLock(payload.lock_s);
    requestAnimationFrame(tick);
    shield.back.focus();
  }

  document.getElementById("btnX").addEventListener("click", () => decide(false));
  document.getElementById("btnMin").addEventListener("click", () => api && api.minimize());
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") decide(false); });

  const DEMO = {
    vi: {
      lock_s: 8,
      view: {
        lang: "vi", level: "HIGH", score: 87, levelLabel: "Khoan đã! Link nguy hiểm", headline: "Giả danh Vietcombank và hối thúc bạn",
        reasonShort: "Đừng đăng nhập hay nhập mã OTP vào trang này.",
        domain: { userinfo: "", prefix: "", decoyPrefix: false, registered: "vcb-digibanks.top", rest: "/xac-nhan", hit: "vcb",
          punycode: "", isIp: false, brand: "Vietcombank", official: "vietcombank.com.vn" },
        officialLine: "Trang chính thức của Vietcombank là vietcombank.com.vn",
        details: [{ icon: "badge", text: "Có tên Vietcombank nhưng không phải trang chính thức" }, { icon: "tag", text: "Đuôi .top hay bị kẻ xấu lợi dụng" },
          { icon: "alert", text: "Có từ hối thúc: “xác nhận”" }],
        checking: false,
        actions: { back: "Quay lại an toàn", proceed: "Vẫn mở link", copy: "Sao chép địa chỉ", report: "Báo cho người gửi", copied: "Đã sao chép địa chỉ",
          reported: "Đã chép lời nhắn, hãy dán vào Zalo", hint: "Nhấn Esc để quay lại", copyText: "https://vcb-digibanks.top/xac-nhan",
          reportText: "Link này có vẻ lừa đảo, bạn đừng bấm nhé: vcb-digibanks[.]top" },
        labels: { caption: "Link này thật sự dẫn tới", why: "Xem vì sao", checking: "Đang xác minh tuổi tên miền…",
          proceedWait: "Vẫn mở link (mở khóa sau {n} giây)", decoy: "phần ngụy trang", ip: "dãy số, không phải tên trang" },
      },
    },
    en: {
      lock_s: 8,
      view: {
        lang: "en", level: "HIGH", score: 87, levelLabel: "Hold on! Dangerous link", headline: "Pretends to be Vietcombank and rushes you",
        reasonShort: "Don't sign in or type any OTP code on this page.",
        domain: { userinfo: "", prefix: "", decoyPrefix: false, registered: "vcb-digibanks.top", rest: "/xac-nhan", hit: "vcb",
          punycode: "", isIp: false, brand: "Vietcombank", official: "vietcombank.com.vn" },
        officialLine: "The official Vietcombank site is vietcombank.com.vn",
        details: [{ icon: "badge", text: "Has the name Vietcombank but isn't the official site" }, { icon: "tag", text: "The .top ending is often abused by scammers" },
          { icon: "alert", text: "Has a pressure word: “xác nhận”" }],
        checking: false,
        actions: { back: "Go back to safety", proceed: "Open anyway", copy: "Copy address", report: "Tell the sender", copied: "Address copied",
          reported: "Message copied, paste it into Zalo", hint: "Press Esc to go back", copyText: "https://vcb-digibanks.top/xac-nhan",
          reportText: "This link looks like a scam, please don't tap it: vcb-digibanks[.]top" },
        labels: { caption: "This link really goes to", why: "See why", checking: "Checking how old the domain is…",
          proceedWait: "Open anyway (unlocks in {n} s)", decoy: "disguise", ip: "numbers, not a site name" },
      },
    },
  };

  function demo() {
    if (window.__DEMO__) return window.__DEMO__;
    const payload = JSON.parse(JSON.stringify(location.search.includes("vi") ? DEMO.vi : DEMO.en));
    const level = (location.search.match(/level=(WARN|HIGH|BLOCKED)/) || [])[1];
    if (level) payload.view.level = level;
    if (location.search.includes("checking")) payload.view.checking = true;
    return payload;
  }

  function boot() {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.initial) {
      api = window.pywebview.api;
      api.initial().then(start);
    } else if (location.search.includes("demo")) {
      start(demo());
    }
  }
  I18N.apply("en");
  if (window.pywebview && window.pywebview.api) boot();
  else window.addEventListener("pywebviewready", boot);
  if (location.search.includes("demo")) window.addEventListener("DOMContentLoaded", boot);
})();
