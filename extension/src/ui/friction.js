// @ts-check
/**
 * Màn hình "Khoan đã!" (Intentional Friction) dùng chung cho content script trên Zalo Web và trang cảnh báo.
 * Giao diện (``shield.js`` + ``shield-css.js``) là bản chép của Desktop: cùng bố cục, cùng màu, cùng chữ.
 * File này chỉ lo phần BẢO MẬT bao quanh:
 *
 * Chống bấm theo phản xạ và chống tự động bấm:
 * - giao diện nằm trong Shadow DOM ở chế độ ``closed`` (script của trang không đọc/sửa/bấm hộ được) và
 *   trong ``<dialog>`` modal ở top layer (không bị phần tử nào của trang che, phần còn lại bị vô hiệu);
 * - nút "vẫn mở" bị khóa đếm ngược, không nhận phím (Enter/Space cho ``click`` có ``detail = 0``), chỉ
 *   nhận cú bấm chuột/chạm thật (``isTrusted``) mà lúc nhấn xuống đã qua thời gian khóa;
 * - service worker kiểm tra lại vé và thời gian khóa trước khi mở, nên kể cả khi bị vượt mặt ở đây
 *   thì liên kết cũng không mở sớm được.
 *
 * File này là script thường (không phải module) vì content script không nạp được ES module; nó gắn
 * ``globalThis.ChottoFriction``. Không nạp font từ extension vào trang Zalo (tránh để lộ URL tài nguyên của
 * extension cho trang): trên Zalo dùng font hệ thống thay thế, trang cảnh báo của extension dùng font đóng gói.
 */
(() => {
  if (/** @type {any} */ (globalThis).ChottoFriction) return;

  const TICK_MS = 100;
  const REASON_TEXT = {
    locked: "Nút vẫn đang khóa, vui lòng đợi hết thời gian đếm ngược.",
    expired: "Phiên kiểm tra đã hết hạn. Hãy đóng lại và bấm vào liên kết lần nữa.",
    "wrong-tab": "Phiên kiểm tra không thuộc tab này. Hãy bấm vào liên kết lần nữa.",
    untrusted: "Chỉ chấp nhận cú bấm chuột thật.",
    unavailable: "CHOTTO đang khởi động lại. Hãy đóng và bấm vào liên kết lần nữa.",
  };

  const STYLE = `
    :host { all: initial; }
    * { box-sizing: border-box; }
    dialog {
      width: min(560px, calc(100vw - 24px)); max-height: calc(100vh - 24px); overflow: auto; margin: auto; padding: 0;
      border: 0; border-radius: 26px; background: transparent; color: inherit; overscroll-behavior: contain;
      box-shadow: 0 0 0 1px rgba(128,120,108,.35), 0 32px 80px rgba(0,0,0,.55);
      animation: rise .35s cubic-bezier(.2,.7,.2,1) both;
    }
    dialog::backdrop { background: rgba(6,5,4,.74); backdrop-filter: blur(3px); }
    @keyframes rise { from { opacity: 0; transform: translateY(10px) scale(.99); } }
    @media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
    .toast { position: fixed; top: 16px; right: 16px; z-index: 2147483647; background: #0c0a08; color: #f4efe7;
      border: 1px solid #c9a45a; border-radius: 999px; padding: 10px 18px;
      font: 13px/1.4 "Onest", "Segoe UI", system-ui, -apple-system, Roboto, sans-serif; box-shadow: 0 8px 24px rgba(0,0,0,.4); }
  `;

  /**
   * Tạo phần tử với nội dung chữ (không bao giờ dùng innerHTML với dữ liệu).
   * @param {string} tag
   * @param {string} [className]
   * @param {string} [text]
   * @returns {HTMLElement}
   */
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  /**
   * Tạo host + shadow root đóng.
   * @param {Element} parent
   * @returns {{host: HTMLElement, root: ShadowRoot}}
   */
  function mountHost(parent) {
    const host = document.createElement("chotto-shield");
    host.style.setProperty("all", "initial", "important");
    const root = host.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    const shieldCss = /** @type {any} */ (globalThis).CHOTTO_SHIELD_CSS;
    style.textContent = `${typeof shieldCss === "string" ? shieldCss : ""}\n${STYLE}`;
    root.append(style);
    parent.append(host);
    return { host, root };
  }

  /**
   * Hiện màn hình friction.
   * @param {object} options
   * @param {any} options.view Nội dung đã chuẩn bị bởi service worker (``view.js``: ``buildView``).
   * @param {number} options.lockMs Thời gian khóa nút "vẫn mở".
   * @param {(choice: "proceed" | "back", trusted: boolean) => Promise<{ok: boolean, reason?: string}>} options.decide
   * @param {Element} [options.parent] Nơi gắn (mặc định ``document.documentElement``).
   * @returns {{close: () => void}}
   */
  function show({ view, lockMs, decide, parent }) {
    const { host, root } = mountHost(parent ?? document.documentElement);
    const dialog = /** @type {HTMLDialogElement} */ (el("dialog"));
    root.append(dialog);
    const shield = /** @type {any} */ (globalThis).ChottoShield.mount(dialog, view, { idPrefix: "chotto" });
    dialog.setAttribute("aria-labelledby", shield.headlineId);
    /** @type {HTMLButtonElement} */
    const back = shield.back;
    /** @type {HTMLButtonElement} */
    const proceed = shield.proceed;
    proceed.tabIndex = -1;

    const startedAt = performance.now();
    const unlockAt = startedAt + Math.max(0, lockMs);
    let pointerDownAt = -Infinity;
    let busy = false;
    let closed = false;

    const render = () => {
      const left = unlockAt - performance.now();
      shield.setLock(Math.max(0, Math.ceil(left / 1000)), left / Math.max(1, unlockAt - startedAt));
    };
    render();
    const timer = setInterval(render, TICK_MS);

    const close = () => {
      if (closed) return;
      closed = true;
      clearInterval(timer);
      try {
        if (dialog.open) dialog.close();
      } catch (error) {
        console.warn("CHOTTO: không đóng được hộp thoại", error);
      }
      host.remove();
    };

    /**
     * @param {"proceed" | "back"} choice
     * @param {boolean} trusted
     */
    const submit = async (choice, trusted) => {
      if (busy || closed) return;
      busy = true;
      try {
        const answer = await decide(choice, trusted);
        if (answer.ok || choice === "back") close();
        else shield.note(/** @type {Record<string, string>} */ (REASON_TEXT)[answer.reason ?? ""] ?? REASON_TEXT.unavailable);
      } catch (error) {
        console.error("CHOTTO: lỗi gửi quyết định", error);
        if (choice === "back") close();
        else shield.note(REASON_TEXT.unavailable);
      } finally {
        busy = false;
      }
    };

    back.addEventListener("click", () => submit("back", true));
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      submit("back", true);
    });
    proceed.addEventListener("pointerdown", (event) => {
      if (event.isTrusted) pointerDownAt = performance.now();
    });
    proceed.addEventListener("keydown", (event) => event.preventDefault());
    proceed.addEventListener("click", (event) => {
      // detail = 0: click sinh từ bàn phím hoặc từ script; isTrusted = false: click giả.
      if (!event.isTrusted || event.detail === 0) return;
      const now = performance.now();
      if (now < unlockAt || pointerDownAt < unlockAt) {
        shield.note(REASON_TEXT.locked);
        return;
      }
      submit("proceed", true);
    });

    try {
      dialog.showModal();
    } catch (error) {
      console.warn("CHOTTO: showModal lỗi, hiện dạng thường", error);
      dialog.setAttribute("open", "");
    }
    back.focus({ preventScroll: true });
    return { close };
  }

  /**
   * Thông báo nhỏ "đang kiểm tra" (cũng trong Shadow DOM đóng).
   * @param {string} text
   * @returns {{remove: () => void}}
   */
  function toast(text) {
    const { host, root } = mountHost(document.documentElement);
    const box = el("div", "toast", text);
    box.setAttribute("role", "status");
    root.append(box);
    return { remove: () => host.remove() };
  }

  /** @type {any} */ (globalThis).ChottoFriction = Object.freeze({ show, toast });
})();
