// Màn hình đệm. Dữ liệu đến từ Python (chotto/webhost.py) qua pywebview:
//   api.initial()        -> {view, lock_s, theme}   (view: chotto/shield.shield_view, có view.lang)
//   api.decide(proceed, pin, rev) -> {ok, need_pin?, auth?, guardian?, stale?}  (Python tự kiểm lại thời gian khóa,
//     Guardian Mode và rev = phiên bản dữ liệu đang hiển thị: bấm trên bản cũ thì bị từ chối)
//   view.guardian = {policy: "pin"|"deny", message, pinLabel} khi Guardian Mode đang chặn (chỉ Desktop)
//   window.CHOTTO.update({view, lock_s, theme}) do Python gọi khi Tầng 3 xong (mức chỉ tăng, bố cục không nhảy)
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
  let guard = null;        // view.guardian
  let shownRev = -1;       // payload.rev đang hiển thị (bản đến muộn hơn bản đã vẽ thì bỏ)

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
    if (proceed && guard && guard.policy === "deny") return;
    deciding = true;
    let reply = null;
    try {
      if (proceed && guard) {                     // mở bằng PIN giám hộ
        const done = api && await window.ChottoGuardian.askPin(api,
          { title: guard.pinLabel, attempt: (pin) => api.decide(true, pin, shownRev) });
        reply = done ? done.reply : null;
      } else {
        reply = api ? await api.decide(proceed, "", shownRev) : { ok: true };
      }
    } catch (err) {
      reply = null;
    }
    if (reply && reply.ok) return;
    deciding = false;
    if (reply && reply.stale && api) {            // trang đang giữ bản cũ (bản đẩy bị lỡ): lấy bản hiện hành
      try { const now = await api.initial(); if (now && now.rev > shownRev) applyLatest(now); } catch (err) { /* thử lại lần bấm sau */ }
    }                             // Python từ chối (còn khóa, hủy nhập PIN...): cho bấm lại sau
    // Chính sách giám hộ đổi khi màn hình đã mở (vừa bật Guardian, hay đổi "mở bằng PIN" thành "khóa hẳn"):
    // Python gửi kèm phần giám hộ mới, hiện ngay và hỏi PIN nếu được mở bằng PIN.
    const fresh = reply && reply.guardian;
    if (fresh && (!guard || guard.policy !== fresh.policy)) {
      guard = fresh;
      shield.update(guardedView(lastView));
      showGuard();
      if (reply.need_pin) decide(true);
    }
  }

  let lastView = null;
  function guardedView(view) {
    if (!(guard && guard.policy === "pin")) return view;
    return { ...view, actions: { ...view.actions, proceed: guard.pinLabel }, labels: { ...view.labels, proceedWait: `${guard.pinLabel} ({n})` } };
  }

  function show({ view, theme, rev }) {
    if (typeof rev === "number") shownRev = rev;
    document.documentElement.dataset.theme = theme === "dark" ? "dark" : "light";
    if (view.lang && view.lang !== I18N.lang) I18N.apply(view.lang);
    document.documentElement.lang = view.lang || "en";
    guard = view.guardian || (shownLevel ? guard : null);
    lastView = view;
    view = guardedView(view);
    if (shield) shield.update(view);
    else {
      shield = window.ChottoShield.mount(document.getElementById("scroll"), view, { theme: document.documentElement.dataset.theme });
      shield.back.addEventListener("click", () => decide(false));
      shield.proceed.addEventListener("click", () => decide(true));
      guardCopy();
    }
    shownLevel = view.level;
    showGuard();
  }

  // Nút "chép địa chỉ": hỏi Python theo cấu hình HIỆN TẠI trước khi chép (Guardian có thể vừa bật ở cửa sổ khác).
  function guardCopy() {
    const copy = shield.root.querySelector(".sh-ghost:not(.sh-report)");
    if (!copy) return;
    let pass = false;
    copy.addEventListener("click", (e) => {
      if (pass || !api || !api.copy_allowed) return;      // demo: không có Python
      e.stopImmediatePropagation();
      e.preventDefault();
      api.copy_allowed().then((reply) => {
        if (!reply || !reply.ok) {                // không được chép: áp bản có phần giám hộ (ẩn nút, khóa bôi đen)
          if (reply && reply.payload && reply.payload.rev > shownRev) applyLatest(reply.payload);
          return;
        }
        pass = true;
        copy.click();
        pass = false;
      }).catch(() => {});
    }, true);
  }

  // Lời nhắn giám hộ; ẩn nút chép địa chỉ (đường lách), mức cấm thì bỏ hẳn nút "vẫn mở".
  function showGuard() {
    if (!guard) return;
    let banner = document.querySelector(".gd-banner");
    if (!banner) {
      banner = document.createElement("p");
      banner.className = "gd-banner";
      banner.setAttribute("role", "note");
      shield.back.before(banner);
    }
    banner.textContent = guard.message;
    document.documentElement.dataset.guard = guard.policy;          // CSS: không cho bôi đen địa chỉ
    const sel = window.getSelection && window.getSelection();
    if (sel) sel.removeAllRanges();
    const copy = shield.root.querySelector(".sh-ghost:not(.sh-report)");
    if (copy) copy.style.display = "none";
    if (guard.policy === "deny") shield.proceed.style.display = "none";
  }

  window.CHOTTO = {
    update(payload) {
      if (typeof payload.rev === "number" && payload.rev <= shownRev) return;   // bản cũ đến muộn
      if (!shield) { opened = opened || performance.now(); show(payload); setLock(payload.lock_s); return; }   // đến trước initial()
      applyLatest(payload);                                // mức vừa tăng: hỏi lại từ đầu theo chính sách mới
    },
  };

  // Bản mới hơn bản đang hiển thị (theo rev): vẽ lại; mức đổi thì hỏi lại từ đầu và kéo dài khóa.
  function applyLatest(payload) {
    const rising = payload.view.level !== shownLevel;
    if (rising) window.ChottoGuardian.close();
    show(payload);
    if (rising) setLock(payload.lock_s);
  }

  function start(payload) {
    opened = opened || performance.now();
    if (!(typeof payload.rev === "number" && payload.rev < shownRev)) {   // bản cập nhật đến trước initial(): giữ bản mới
      show(payload);
      setLock(payload.lock_s);
    }
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
    const policy = (location.search.match(/guard=(pin|deny)/) || [])[1];
    if (policy) {
      payload.view.guardian = payload.view.lang === "vi"
        ? { policy, message: "Đang bật Bảo vệ Gia đình. Nếu cần mở, hãy nhờ Mẹ (0901 234 567) kiểm tra giúp nhé!", pinLabel: "Nhập mã PIN giám hộ để mở" }
        : { policy, message: "Family Protection is on. If you need this link, ask Mum (0901 234 567) to check it for you!", pinLabel: "Enter guardian PIN to open" };
    }
    payload.theme = new URLSearchParams(location.search).get("theme");
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
