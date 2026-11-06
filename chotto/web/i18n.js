// Từ điển giao diện (en, vi) dùng chung cho app.html và friction.html. Mặc định tiếng Anh.
//   data-i18n="key"                 thay textContent
//   data-i18n-html="key"            thay innerHTML (chuỗi tĩnh của chính từ điển, không có dữ liệu người dùng)
//   data-i18n-attr="attr:key;..."   thay thuộc tính (aria-label, placeholder...)
// Chữ do JavaScript sinh ra dùng CHOTTO_I18N.t(key, {biến}).
"use strict";
(() => {
  const STRINGS = {
    en: {
      "nav.home": "Overview", "nav.check": "Check a link", "nav.log": "Activity", "nav.settings": "Settings",
      "nav.aria": "Main sections", "footer": "Developed by AECCUS", "lang.aria": "Language",
      "win.min": "Minimize", "win.max": "Maximize", "win.close": "Close window",
      "home.h": "Overview", "home.sub": "Every link you tap in Zalo goes through Chotto before it opens.",
      "guard.on": "This computer is protected", "guard.off": "Chotto isn’t receiving links from Zalo yet",
      "guard.offText": "Set Chotto as your link handler to start checking.",
      "guard.install": "Set Chotto as link handler", "guard.badge": "Chotto is your link handler", "guard.total": "links checked in the last 7 days",
      "tile.safe": "safe links, opened right away", "tile.safeSub": "nothing for you to do",
      "tile.warned": "warnings shown", "tile.closed": "you closed {n} of them", "tile.none": "no suspicious links yet",
      "tile.blocked": "known scam links", "tile.blockedSub": "on the scam list",
      "recent.h": "Recent", "recent.empty": "No links yet. Links you tap in Zalo will show up here.",
      "log.off": "The activity log is off. Turn it on in Settings to see checked links.",
      "check.h": "Check a link", "check.sub": "Paste a link someone sent you. Chotto checks it without opening the page.",
      "check.placeholder": "Paste a link here", "check.aria": "Link to check", "check.btn": "Check",
      "check.busy": "Checking…", "check.fail": "Couldn’t check", "check.error": "Something went wrong, please try again",
      "check.safe": "Safe", "check.safeText": "No signs of a scam. Still, never enter an OTP code on an unfamiliar page.",
      "check.suspicious": "Suspicious", "check.danger": "Dangerous",
      "official": "The real {brand} site is <strong>{domain}</strong>",
      "log.h": "Activity", "log.sub": "Only domain names are kept on this computer, never full addresses or content.",
      "log.export": "Export to CSV",
      "set.h": "Settings", "set.sub": "Changes are saved right away.", "set.privacy": "Privacy",
      "set.tier3": "Look up domain age online", "set.tier3Sub": "Turn off to keep Chotto fully offline",
      "set.log": "Keep an activity log on this computer", "set.logSub": "Domain names only, so you can review them",
      "set.suspicious": "When a link looks suspicious", "set.advice": "Show advice",
      "set.adviceSub": "Tips on what to do, generated on this computer",
      "set.unknown": "Also check links from unknown sources", "set.unknownSub": "Links that may not come from Zalo",
      "set.wait": "Wait before “Open anyway” unlocks",
      "set.waitSub": "Time to think it over; dangerous links wait 3 to 5 seconds longer", "sec": "{n} sec",
      "set.waitAria": "Waiting time", "set.language": "Language",
      "set.languageSub": "Used in every Chotto window", "set.general": "General",
      "act.install": "Set as link handler", "act.installed": "✓ Chotto is your link handler", "act.update": "Update scam list",
      "act.uninstall": "Stop using Chotto as link handler", "act.busy": "Working…",
      "confirm.uninstall": "Stop using Chotto as your link handler?\n\nLinks in Zalo will then open directly without being checked. You’ll need to pick your default browser again in system settings.",
      "saved": "Saved", "saveFail": "Couldn’t save settings",
      "dec.auto_open": "Safe", "dec.cancel": "You closed it", "dec.proceed": "You opened it",
      "dec.ui_failed_blocked": "Blocked", "dec.ui_failed_open": "Opened",
      "today": "Today, {t}", "yesterday": "Yesterday, {t}",
      // màn hình đệm
      "f.tb": "Chotto · link from Zalo", "f.min": "Minimize", "f.x": "Close without opening the link",
      "f.hold": "Hold on.", "f.score": "risk score out of 100", "f.safe": "Safe", "f.suspicious": "Suspicious",
      "f.dangerous": "Dangerous", "f.anatomy": "Where this link really goes", "f.whyBlock": "Why Chotto stopped it",
      "f.whyWarn": "Why Chotto is warning you", "f.checking": "Checking the domain’s age…", "f.source": "Detected by: {s}",
      "f.advice": "What to do", "f.call": "If in doubt, call the sender to ask.",
      "f.hint": "Press <kbd>Esc</kbd> to close", "f.openIn": "Open anyway in {n} s", "f.open": "Open anyway",
      "f.close": "Close, don’t open",
    },
    vi: {
      "nav.home": "Tổng quan", "nav.check": "Kiểm tra link", "nav.log": "Nhật ký", "nav.settings": "Cài đặt",
      "nav.aria": "Mục chính", "footer": "Được phát triển bởi AECCUS", "lang.aria": "Ngôn ngữ",
      "win.min": "Thu nhỏ", "win.max": "Phóng to", "win.close": "Đóng cửa sổ",
      "home.h": "Tổng quan", "home.sub": "Mọi link bấm trong Zalo đều đi qua Chotto trước khi mở.",
      "guard.on": "Máy này đang được bảo vệ", "guard.off": "Chotto chưa nhận link từ Zalo",
      "guard.offText": "Đặt Chotto làm trình mở link để bắt đầu kiểm tra.",
      "guard.install": "Đặt Chotto làm trình mở link", "guard.badge": "Đã đặt Chotto làm trình mở link", "guard.total": "link đã kiểm tra trong 7 ngày",
      "tile.safe": "link an toàn, mở ngay", "tile.safeSub": "không cần bạn làm gì",
      "tile.warned": "lần cảnh báo", "tile.closed": "bạn đã đóng {n} lần", "tile.none": "chưa có link đáng ngờ nào",
      "tile.blocked": "link lừa đảo đã biết", "tile.blockedSub": "có trong danh sách lừa đảo",
      "recent.h": "Gần đây", "recent.empty": "Chưa có link nào. Khi bạn bấm link trong Zalo, nó sẽ hiện ở đây.",
      "log.off": "Nhật ký đang tắt. Bật lại trong Cài đặt nếu bạn muốn xem link đã kiểm tra.",
      "check.h": "Kiểm tra một link", "check.sub": "Dán link ai đó gửi bạn. Chotto kiểm tra mà không mở trang.",
      "check.placeholder": "Dán link vào đây", "check.aria": "Link cần kiểm tra", "check.btn": "Kiểm tra",
      "check.busy": "Đang kiểm tra…", "check.fail": "Không kiểm tra được", "check.error": "Đã có lỗi, hãy thử lại",
      "check.safe": "An toàn", "check.safeText": "Không thấy dấu hiệu lừa đảo. Vẫn đừng nhập mã OTP vào trang lạ.",
      "check.suspicious": "Đáng ngờ", "check.danger": "Nguy hiểm",
      "official": "Trang thật của {brand} là <strong>{domain}</strong>",
      "log.h": "Nhật ký", "log.sub": "Chỉ lưu tên miền trên máy bạn, không lưu đường dẫn hay nội dung.",
      "log.export": "Xuất ra file CSV",
      "set.h": "Cài đặt", "set.sub": "Thay đổi được lưu ngay.", "set.privacy": "Quyền riêng tư",
      "set.tier3": "Tra tuổi tên miền qua mạng", "set.tier3Sub": "Tắt đi thì Chotto chạy hoàn toàn ngoại tuyến",
      "set.log": "Ghi nhật ký trên máy", "set.logSub": "Chỉ lưu tên miền, để bạn xem lại",
      "set.suspicious": "Khi gặp link đáng ngờ", "set.advice": "Hiện lời khuyên",
      "set.adviceSub": "Gợi ý việc nên làm, tạo ngay trên máy bạn",
      "set.unknown": "Kiểm tra cả link không rõ nguồn", "set.unknownSub": "Link không chắc đến từ Zalo",
      "set.wait": "Thời gian chờ trước khi được mở",
      "set.waitSub": "Để bạn kịp nghĩ lại; link nguy hiểm chờ thêm 3 đến 5 giây", "sec": "{n} giây",
      "set.waitAria": "Thời gian chờ", "set.language": "Ngôn ngữ",
      "set.languageSub": "Áp dụng cho mọi cửa sổ Chotto", "set.general": "Chung",
      "act.install": "Đặt làm trình mở link", "act.installed": "✓ Đã đặt Chotto làm trình mở link", "act.update": "Cập nhật danh sách lừa đảo",
      "act.uninstall": "Gỡ Chotto khỏi trình mở link", "act.busy": "Đang thực hiện…",
      "confirm.uninstall": "Gỡ Chotto khỏi vai trò trình mở link?\n\nSau đó link trong Zalo sẽ mở thẳng, không được kiểm tra. Bạn cần chọn lại trình duyệt mặc định trong Cài đặt của hệ thống.",
      "saved": "Đã lưu", "saveFail": "Không lưu được cài đặt",
      "dec.auto_open": "An toàn", "dec.cancel": "Bạn đã đóng", "dec.proceed": "Bạn vẫn mở",
      "dec.ui_failed_blocked": "Đã chặn", "dec.ui_failed_open": "Đã mở",
      "today": "Hôm nay, {t}", "yesterday": "Hôm qua, {t}",
      "f.tb": "Chotto · link mở từ Zalo", "f.min": "Thu nhỏ", "f.x": "Đóng, không mở link",
      "f.hold": "Khoan đã.", "f.score": "điểm rủi ro trên 100", "f.safe": "An toàn", "f.suspicious": "Đáng ngờ",
      "f.dangerous": "Nguy hiểm", "f.anatomy": "Link này thật ra dẫn tới đâu", "f.whyBlock": "Vì sao Chotto chặn lại",
      "f.whyWarn": "Vì sao Chotto cảnh báo", "f.checking": "Đang tra tuổi tên miền…", "f.source": "Phát hiện bởi: {s}",
      "f.advice": "Nên làm gì", "f.call": "Nếu nghi ngờ, hãy hỏi người gửi qua một cuộc gọi.",
      "f.hint": "Nhấn <kbd>Esc</kbd> để đóng", "f.openIn": "Vẫn mở link sau {n} giây", "f.open": "Vẫn mở link",
      "f.close": "Đóng, không mở",
    },
  };

  let lang = "en";

  function t(key, vars) {
    const text = (STRINGS[lang] && STRINGS[lang][key]) ?? STRINGS.en[key] ?? key;
    return vars ? text.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)) : text;
  }

  function apply(next) {
    lang = next === "vi" ? "vi" : "en";
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    document.querySelectorAll("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
    document.querySelectorAll("[data-i18n-attr]").forEach((el) => {
      el.dataset.i18nAttr.split(";").forEach((pair) => {
        const [attr, key] = pair.split(":");
        if (attr && key) el.setAttribute(attr.trim(), t(key.trim()));
      });
    });
  }

  window.CHOTTO_I18N = { t, apply, get lang() { return lang; }, locale: () => (lang === "vi" ? "vi-VN" : "en-GB") };
})();
