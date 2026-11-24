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
      "home.week": "This week", "home.h": "Overview", "home.sub": "Every link you tap in Zalo goes through Chotto before it opens.",
      "guard.on": "Protected", "guard.off": "Not protecting yet",
      "guard.offText": "",
      "guard.install": "Set as link handler", "guard.badge": "Link handler set", "guard.total": "Links checked",
      "tile.safe": "Safe", "tile.safeSub": "nothing for you to do",
      "tile.warned": "Warnings", "tile.closed": "{n} closed", "tile.none": "—",
      "tile.blocked": "Scams", "tile.blockedSub": "on the scam list",
      "recent.h": "Recent", "recent.empty": "No links yet.",
      "log.off": "Log is off.",
      "check.h": "Check a link", "check.sub": "Paste a link someone sent you. Chotto checks it without opening the page.",
      "check.placeholder": "Paste a link here", "check.aria": "Link to check", "check.btn": "Check",
      "check.busy": "Checking…", "check.fail": "Couldn’t check", "check.error": "Something went wrong, please try again",
      "check.safe": "Safe", "check.safeText": "No scam signs found.",
      "check.suspicious": "Suspicious", "check.danger": "Dangerous",
      "official": "Real {brand}: <strong>{domain}</strong>",
      "log.h": "Activity", "log.sub": "Only domain names are kept on this computer, never full addresses or content.",
      "log.export": "Export to CSV", "log.clear": "Clear activity log",
      "clear.title": "Clear the activity log?", "clear.body": "Every link Chotto has recorded on this computer will be deleted.", "clear.yes": "Clear",
      "set.h": "Settings", "set.sub": "Changes are saved right away.", "set.privacy": "Privacy",
      "set.tier3": "Domain age lookup", "set.tier3Sub": "Turn off to keep Chotto fully offline",
      "set.log": "Activity log", "set.logSub": "Domain names only, so you can review them",
      "set.suspicious": "Suspicious links", "set.advice": "Show advice",
      "set.adviceSub": "Tips on what to do, generated on this computer",
      "set.unknown": "Unknown sources", "set.unknownSub": "Links that may not come from Zalo",
      "set.wait": "Open-anyway delay",
      "set.waitSub": "Time to think it over; dangerous links wait 3 to 5 seconds longer", "sec": "{n} sec",
      "set.waitAria": "Waiting time", "set.language": "Language",
      "set.languageSub": "Used in every Chotto window", "set.general": "General",
      "act.install": "Set as link handler", "act.installed": "✓ Link handler set", "act.update": "Update scam list",
      "act.uninstall": "Stop using Chotto", "act.busy": "Working…",
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
      "tip.safe": "Safe links open right away. Nothing to do.",
      "tip.warned": "Warnings shown to you.",
      "tip.blocked": "Links on the known scam list.",
      "tip.check": "Paste a link someone sent you. Chotto checks it without opening the page.",
      "tip.log": "Only domain names are kept on this computer, never full addresses or content.",
      "tip.set": "Changes are saved right away.",
      "tip.tier3": "Turn off to keep Chotto fully offline.",
      "tip.logset": "Domain names only, so you can review them.",
      "tip.advice": "Tips on what to do, made on this computer.",
      "tip.unknown": "Also check links that may not come from Zalo.",
      "tip.wait": "Time to think it over. Dangerous links wait 3 to 5 seconds longer.",
      "set.buddy": "Taskbar character", "set.buddyOn": "Show on the taskbar",
      "set.buddyStart": "When to show it", "start.login": "At sign-in", "start.zalo": "With Zalo", "start.off": "Manual",
      "tip.buddyStart": "At sign-in: appears as soon as Windows starts. With Zalo: appears only while Zalo is open. Manual: never starts by itself; turn it on with the switch above, and it turns itself off when you shut down.",
      "set.buddyFps": "Smoothness (frames per second)", "tip.buddyFps": "Drag to choose 10-240. Higher is smoother but uses more CPU and battery. 60 suits most screens; match your monitor refresh rate for the smoothest result.",
      "set.buddyPin": "Keep it in one place", "tip.buddyPin": "The character stops running and stays where you put it.",
      "buddy.place": "Position", "buddy.placeBtn": "Choose position", "buddy.placeDone": "Done",
      "buddy.placeHint": "Drag the character left or right on the taskbar, then press Done.",
      "tip.buddy": "A small companion naps above the taskbar and jumps up when Chotto stops a suspicious link. Right-click it to hide.",
      "buddy.custom": "Customize character", "buddy.preview": "Character preview",
      "buddy.g0": "Hair", "buddy.g1": "Eyes", "buddy.g2": "Skin", "buddy.g3": "Cloak", "buddy.g4": "Dress", "buddy.g5": "Shoes, accessories",
      "buddy.p0": "Sleeping", "buddy.p1": "Startled", "buddy.p2": "Running", "buddy.p3": "Hold on!",
      "buddy.default": "default", "buddy.pick": "Pick any color", "buddy.random": "Random", "buddy.reset": "Reset",
      "buddy.unsupported": "The taskbar character is only available on Windows.",
      "confirm.title": "Remove Chotto?",
      "confirm.body": "Links in Zalo will open without being checked.",
      "confirm.keep": "Keep it",
      "confirm.yes": "Remove",
    },
    vi: {
      "nav.home": "Tổng quan", "nav.check": "Kiểm tra link", "nav.log": "Nhật ký", "nav.settings": "Cài đặt",
      "nav.aria": "Mục chính", "footer": "Được phát triển bởi AECCUS", "lang.aria": "Ngôn ngữ",
      "win.min": "Thu nhỏ", "win.max": "Phóng to", "win.close": "Đóng cửa sổ",
      "home.week": "Tuần này", "home.h": "Tổng quan", "home.sub": "Mọi link bấm trong Zalo đều đi qua Chotto trước khi mở.",
      "guard.on": "Đang được bảo vệ", "guard.off": "Chưa bảo vệ",
      "guard.offText": "",
      "guard.install": "Đặt làm trình mở link", "guard.badge": "Đã đặt trình mở link", "guard.total": "Links đã kiểm tra",
      "tile.safe": "An toàn", "tile.safeSub": "không cần bạn làm gì",
      "tile.warned": "Cảnh báo", "tile.closed": "đóng {n}", "tile.none": "—",
      "tile.blocked": "Lừa đảo", "tile.blockedSub": "có trong danh sách lừa đảo",
      "recent.h": "Gần đây", "recent.empty": "Chưa có link nào.",
      "log.off": "Nhật ký đang tắt.",
      "check.h": "Kiểm tra link", "check.sub": "Dán link ai đó gửi bạn. Chotto kiểm tra mà không mở trang.",
      "check.placeholder": "Dán link vào đây", "check.aria": "Link cần kiểm tra", "check.btn": "Kiểm tra",
      "check.busy": "Đang kiểm tra…", "check.fail": "Không kiểm tra được", "check.error": "Đã có lỗi, hãy thử lại",
      "check.safe": "An toàn", "check.safeText": "Không thấy dấu hiệu lừa đảo.",
      "check.suspicious": "Đáng ngờ", "check.danger": "Nguy hiểm",
      "official": "{brand} thật: <strong>{domain}</strong>",
      "log.h": "Nhật ký", "log.sub": "Chỉ lưu tên miền trên máy bạn, không lưu đường dẫn hay nội dung.",
      "log.export": "Xuất ra file CSV", "log.clear": "Xóa nhật ký",
      "clear.title": "Xóa nhật ký?", "clear.body": "Mọi link Chotto đã ghi trên máy này sẽ bị xóa.", "clear.yes": "Xóa",
      "set.h": "Cài đặt", "set.sub": "Thay đổi được lưu ngay.", "set.privacy": "Quyền riêng tư",
      "set.tier3": "Tra tuổi tên miền", "set.tier3Sub": "Tắt đi thì Chotto chạy hoàn toàn ngoại tuyến",
      "set.log": "Ghi nhật ký", "set.logSub": "Chỉ lưu tên miền, để bạn xem lại",
      "set.suspicious": "Link đáng ngờ", "set.advice": "Hiện lời khuyên",
      "set.adviceSub": "Gợi ý việc nên làm, tạo ngay trên máy bạn",
      "set.unknown": "Nguồn không rõ", "set.unknownSub": "Link không chắc đến từ Zalo",
      "set.wait": "Thời gian chờ mở",
      "set.waitSub": "Để bạn kịp nghĩ lại; link nguy hiểm chờ thêm 3 đến 5 giây", "sec": "{n} giây",
      "set.waitAria": "Thời gian chờ", "set.language": "Ngôn ngữ",
      "set.languageSub": "Áp dụng cho mọi cửa sổ Chotto", "set.general": "Chung",
      "act.install": "Đặt làm trình mở link", "act.installed": "✓ Đã đặt trình mở link", "act.update": "Cập nhật danh sách",
      "act.uninstall": "Gỡ Chotto", "act.busy": "Đang thực hiện…",
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
      "tip.safe": "Link an toàn mở ngay. Bạn không cần làm gì.",
      "tip.warned": "Số lần Chotto cảnh báo bạn.",
      "tip.blocked": "Link có trong danh sách lừa đảo đã biết.",
      "tip.check": "Dán link ai đó gửi bạn. Chotto kiểm tra mà không mở trang.",
      "tip.log": "Chỉ lưu tên miền trên máy bạn, không lưu đường dẫn hay nội dung.",
      "tip.set": "Thay đổi được lưu ngay.",
      "tip.tier3": "Tắt đi thì Chotto chạy hoàn toàn ngoại tuyến.",
      "tip.logset": "Chỉ lưu tên miền để bạn xem lại.",
      "tip.advice": "Gợi ý việc nên làm, tạo ngay trên máy bạn.",
      "tip.unknown": "Kiểm tra cả link có thể không đến từ Zalo.",
      "tip.wait": "Để bạn kịp nghĩ lại. Link nguy hiểm chờ thêm 3 đến 5 giây.",
      "set.buddy": "Nhân vật trên taskbar", "set.buddyOn": "Hiện trên thanh taskbar",
      "set.buddyStart": "Khi nào hiện", "start.login": "Khi đăng nhập", "start.zalo": "Khi mở Zalo", "start.off": "Thủ công",
      "tip.buddyStart": "Khi đăng nhập: hiện ngay khi Windows khởi động. Khi mở Zalo: chỉ hiện lúc Zalo đang mở. Thủ công: không tự chạy, bạn tự bật bằng công tắc phía trên, và công tắc tự về tắt khi bạn tắt máy.",
      "set.buddyFps": "Độ mượt (khung hình/giây)", "tip.buddyFps": "Kéo để chọn từ 10 đến 240. Càng cao càng mượt nhưng tốn CPU và pin hơn. 60 hợp với hầu hết màn hình; đặt bằng tần số quét màn hình của bạn để mượt nhất.",
      "set.buddyPin": "Cố định tại một chỗ", "tip.buddyPin": "Nhân vật thôi chạy và đứng yên ở chỗ bạn đặt.",
      "buddy.place": "Vị trí", "buddy.placeBtn": "Chọn vị trí", "buddy.placeDone": "Xong",
      "buddy.placeHint": "Dùng chuột kéo nhân vật sang trái hoặc phải trên taskbar, rồi bấm Xong.",
      "tip.buddy": "Một nhân vật nhỏ ngủ trên thanh taskbar và bật dậy khi Chotto chặn link đáng ngờ. Bấm chuột phải để ẩn.",
      "buddy.custom": "Tùy chỉnh nhân vật", "buddy.preview": "Xem trước nhân vật",
      "buddy.g0": "Tóc", "buddy.g1": "Mắt", "buddy.g2": "Da", "buddy.g3": "Áo choàng", "buddy.g4": "Váy", "buddy.g5": "Giày, phụ kiện",
      "buddy.p0": "Ngủ", "buddy.p1": "Giật mình", "buddy.p2": "Chạy", "buddy.p3": "Khoan đã!",
      "buddy.default": "mặc định", "buddy.pick": "Chọn màu bất kỳ", "buddy.random": "Ngẫu nhiên", "buddy.reset": "Đặt lại",
      "buddy.unsupported": "Nhân vật trên taskbar hiện chỉ có trên Windows.",
      "confirm.title": "Gỡ Chotto?",
      "confirm.body": "Link trong Zalo sẽ mở thẳng, không được kiểm tra.",
      "confirm.keep": "Giữ lại",
      "confirm.yes": "Gỡ",
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
    document.querySelectorAll("[data-i18n-tip]").forEach((el) => {
      const text = t(el.dataset.i18nTip);
      el.dataset.tip = text;
      el.setAttribute("aria-label", text);
    });
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
