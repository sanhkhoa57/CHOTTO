// @ts-check
/**
 * Giao diện Guardian mode cho người lớn tuổi: hai màn hình, ít lựa chọn, chữ đời thường.
 *
 * Màn hình 1 (chặn): một câu kết luận + tên trang web + CHỈ HAI nút ("Đóng", "Nhờ người giám hộ xem giúp").
 *   "Sao chép địa chỉ", "Báo cho người gửi", "Xem vì sao" gom vào liên kết nhỏ "Thêm lựa chọn" (thu gọn).
 * Màn hình 2 (đã nhờ): một chạm tạo lời nhắn và TỰ CHÉP vào clipboard (câu ngắn + tên trang web + liên kết tới trang người
 *   giám hộ); hướng dẫn một dòng; MỘT ô nhập số lớn + nút "Mở link". Phương án dự phòng (đọc mã bằng miệng + hình vuông quét
 *   bằng camera) thu gọn trong "Không gửi được tin nhắn?".
 *
 * Giao diện CHỈ hiển thị: mọi quyết định (mã đúng/sai, khóa, hết hạn) do service worker đưa ra.
 * Script thường (content script không nạp được ES module); gắn ``globalThis.ChottoGuardianUI``. Mọi chuỗi gán bằng
 * ``textContent``; hình vuông quét dựng bằng DOM SVG. Truy cập: nhãn, ``aria-live`` cho lỗi/trạng thái, bàn phím đầy đủ,
 * không phụ thuộc màu (mỗi trạng thái đều có chữ), không có hoạt ảnh (tôn trọng ``prefers-reduced-motion``).
 * Chữ dùng trong giao diện: "người giám hộ", "trang web", "mã"; KHÔNG dùng thuật ngữ kỹ thuật và KHÔNG xưng hô theo vai.
 */
(() => {
  if (/** @type {any} */ (globalThis).ChottoGuardianUI) return;

  const SVG_NS = "http://www.w3.org/2000/svg";
  const DIGITS = 6;
  const MAX_ATTEMPTS = 5;
  const MAX_NAME = 30;
  /** Chỉ nhắc hạn khi còn dưới ngần này (không có đồng hồ đếm ngược gây áp lực ở màn hình chính). */
  const REMIND_MS = 2 * 60_000;
  const UNSAFE_CHARS = /[\p{Cc}\p{Cf}\p{Co}\p{Cs}\p{Zl}\p{Zp}]/gu;

  const TEXT = Object.freeze({
    headline: "Link này có thể là lừa đảo. Đừng mở.",
    headlineWarn: "Link này đáng ngờ. Nên hỏi người giám hộ trước.",
    close: "Đóng",
    askDefault: "Nhờ người giám hộ xem giúp",
    askPrefix: "Nhờ ",
    askSuffix: " xem giúp",
    more: "Thêm lựa chọn",
    // Màn hình 2
    titleDefault: "Gửi lời nhắn cho người giám hộ",
    titlePrefix: "Gửi lời nhắn cho ",
    copied: "Đã chép lời nhắn.",
    copiedAgain: "Đã chép lại lời nhắn.",
    copyFailed: "Chưa chép được lời nhắn. Bấm “Chép lại”.",
    how: "Mở Zalo, dán vào cuộc trò chuyện với người giám hộ rồi gửi.",
    copyAgain: "Chép lại",
    codeIntro: "Người giám hộ sẽ trả lời bằng 6 số. Nhập vào đây:",
    codeLabel: "6 số do người giám hộ gửi",
    open: "Mở link",
    trust: "Chỉ người giám hộ của bạn mới đưa được số này. Ai gọi điện hỏi mã của bạn là kẻ lừa đảo.",
    fallbackToggle: "Không gửi được tin nhắn?",
    fallbackIntro: "Hãy gọi điện cho người giám hộ (số bạn đã lưu) và đọc cho họ:",
    siteCaption: "Trang web",
    codeCaption: "Mã (đọc từng nhóm 4 ký tự)",
    scanIntro: "Hoặc để họ quét hình vuông này bằng camera điện thoại:",
    scanLabel: "Hình vuông để người giám hộ quét bằng camera điện thoại",
    fallbackOutro: "Họ sẽ đọc lại cho bạn 6 số. Nhập vào ô phía trên.",
    loading: "Đang tạo lời nhắn…",
    renew: "Tạo lời nhắn mới",
    expiresSoon: (/** @type {string} */ t) => `Lời nhắn sắp hết hạn (còn ${t}).`,
    wrong: (/** @type {number} */ n) => `Mã chưa đúng. Còn ${n} lần thử.`,
    format: "Mã gồm đúng 6 số. Bạn gõ lại giúp nhé.",
    locked: "Đã nhập sai quá nhiều lần.",
    lockedIn: (/** @type {string} */ t) => `Thử lại sau ${t}.`,
    lockedEnd: "Hết thời gian chờ. Bạn có thể tạo lời nhắn mới.",
    gone: "Lời nhắn đã hết hạn hoặc bị hủy. Hãy tạo lời nhắn mới.",
    destroyed: `Đã nhập sai ${MAX_ATTEMPTS} lần nên lời nhắn bị hủy. Hãy tạo lời nhắn mới.`,
    mismatch: "Lời nhắn này không thuộc link đang mở. Hãy tạo lời nhắn mới.",
    misconfigured: "Chế độ người giám hộ chưa được cài đúng nên link này không thể mở. Hãy báo người giám hộ của bạn.",
    unavailable: "CHOTTO chưa trả lời được. Hãy thử lại.",
    ok: "Đã được cho phép. Đang mở link…",
  });

  /**
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
   * @param {number} ms
   * @returns {string} ``m:ss``.
   */
  function clock(ms) {
    const total = Math.max(0, Math.ceil(ms / 1000));
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
  }

  /**
   * Tên người giám hộ hiển thị: lọc ký tự điều khiển/vô hình/đảo chiều, gộp khoảng trắng, tối đa 30 ký tự
   * (cùng quy tắc với ``sanitizeName`` của share.js; lọc lần nữa ở đây phòng thủ nhiều lớp). Luôn gán bằng ``textContent``.
   * @param {unknown} value
   * @returns {string | null}
   */
  function cleanName(value) {
    if (typeof value !== "string") return null;
    const text = value.replace(UNSAFE_CHARS, " ").replace(/\s+/g, " ").trim();
    const limited = Array.from(text).slice(0, MAX_NAME).join("").trim();
    return limited === "" ? null : limited;
  }

  /**
   * Mã người dùng gõ/dán: lấy các chữ số; đúng 6 số thì hợp lệ ("123 456", "123-456", cả câu dán nguyên).
   * @param {string} text
   * @returns {string | null}
   */
  function normalizeCode(text) {
    const digits = String(text).replace(/\D/g, "");
    return digits.length === DIGITS ? digits : null;
  }

  /**
   * @param {string | null} name
   * @returns {string} Chữ trên nút xin phép (dạng thuần, cho nhãn truy cập).
   */
  function askText(name) {
    return name ? `${TEXT.askPrefix}${name}${TEXT.askSuffix}` : TEXT.askDefault;
  }

  /**
   * View cho màn hình 1: một câu kết luận lớn, không câu phụ, nút chính là "Đóng".
   * @param {any} view ``ShieldView`` gốc.
   * @param {unknown} [name] Tên người giám hộ (tùy chọn).
   * @returns {any}
   */
  function blockView(view, name) {
    const actions = { ...(view.actions ?? {}), back: TEXT.close, hint: "", proceed: askText(cleanName(name)) };
    return { ...view, headline: view.level === "WARN" ? TEXT.headlineWarn : TEXT.headline, reasonShort: "", actions };
  }

  /**
   * Sắp lại màn hình 1 do ``ChottoShield`` dựng: chỉ còn hai nút chính; phần còn lại vào "Thêm lựa chọn" (thu gọn).
   * @param {{root: HTMLElement}} shield
   * @param {unknown} [name]
   * @returns {void}
   */
  function arrange(shield, name) {
    const root = shield.root;
    root.dataset.guardian = "";
    root.dataset.step = "1";
    const pick = (/** @type {string} */ selector) => /** @type {HTMLElement | null} */ (root.querySelector(selector));
    const actions = pick(".sh-actions");
    const more = pick(".sh-more");
    const note = pick(".sh-note");
    const hint = pick(".sh-hint");
    const whyBtn = pick(".sh-whybtn");
    const whyBody = pick(".sh-whybody");
    const ask = pick(".sh-proceed");
    if (!actions || !more || !note || !whyBtn || !whyBody) return;
    hint?.remove();
    const label = ask?.lastElementChild;
    const clean = cleanName(name);
    if (label && clean) {
      label.replaceChildren(document.createTextNode(TEXT.askPrefix), el("b", "gd-name", clean), document.createTextNode(TEXT.askSuffix));
    }
    const toggle = /** @type {HTMLButtonElement} */ (el("button", "gd-more-toggle", TEXT.more));
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    const body = el("div", "gd-more-body");
    body.id = "chotto-gd-more";
    body.hidden = true;
    toggle.setAttribute("aria-controls", body.id);
    body.append(more, whyBtn, whyBody, note);
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      body.hidden = !open;
    });
    actions.after(toggle, body);
  }

  /**
   * Chuyển bước. Sang bước 2 thì ẩn mọi thứ của màn hình 1 (CSS) và xóa dòng trạng thái cũ ("Đã chép địa chỉ"…).
   * @param {{root: HTMLElement, note?: (text: string) => void}} shield
   * @param {1 | 2} step
   */
  function setStep(shield, step) {
    shield.root.dataset.step = String(step);
    if (step === 2) shield.note?.("");
  }

  /**
   * Hình vuông quét bằng camera, dạng SVG (nền trắng, điểm đen, viền yên tĩnh 4 ô) từ thư viện qrcode-generator đã đóng gói.
   * @param {string} text
   * @returns {SVGElement | null} ``null`` nếu thư viện không có hoặc nội dung quá dài.
   */
  function qrSvg(text) {
    const factory = /** @type {any} */ (globalThis).qrcode;
    if (typeof factory !== "function") return null;
    try {
      const qr = factory(0, "M");
      qr.addData(text);
      qr.make();
      const n = qr.getModuleCount();
      const quiet = 4;
      const size = n + quiet * 2;
      let d = "";
      for (let y = 0; y < n; y++) {
        for (let x = 0; x < n; x++) {
          if (!qr.isDark(y, x)) continue;
          let run = 1;
          while (x + run < n && qr.isDark(y, x + run)) run++;
          d += `M${x + quiet} ${y + quiet}h${run}v1h-${run}z`;
          x += run - 1;
        }
      }
      const svg = document.createElementNS(SVG_NS, "svg");
      svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
      svg.setAttribute("shape-rendering", "crispEdges");
      svg.setAttribute("role", "img");
      svg.setAttribute("aria-label", TEXT.scanLabel);
      const bg = document.createElementNS(SVG_NS, "rect");
      bg.setAttribute("width", String(size));
      bg.setAttribute("height", String(size));
      bg.setAttribute("fill", "#ffffff");
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", d);
      path.setAttribute("fill", "#000000");
      // .sh svg (shield.css) vẽ biểu tượng bằng nét viền; hình vuông quét phải là ô đặc, không viền.
      bg.style.stroke = path.style.stroke = "none";
      svg.append(bg, path);
      return svg;
    } catch {
      return null;
    }
  }

  /**
   * Chép chữ vào clipboard (API hiện đại; rơi về ``execCommand`` khi trang không cho phép).
   * @param {string} text
   * @param {Element} scope Nơi gắn ô nhập tạm (chạy được trong Shadow DOM).
   * @returns {Promise<boolean>}
   */
  async function copyText(text, scope) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      /* rơi xuống cách cũ */
    }
    const box = /** @type {HTMLTextAreaElement} */ (el("textarea"));
    box.value = text;
    box.setAttribute("readonly", "");
    box.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0";
    scope.append(box);
    box.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    box.remove();
    return ok;
  }

  /**
   * @typedef {object} ChallengeView
   * @property {"challenge"} state
   * @property {string} domain
   * @property {string} nonceText
   * @property {string} qr Nội dung hình vuông quét (liên kết tới trang người giám hộ).
   * @property {string} message Lời nhắn soạn sẵn để dán vào Zalo.
   * @property {number} expiresAt
   * @property {number} attemptsLeft
   */

  /**
   * Dựng màn hình 2 vào ``container``.
   * @param {Element} container
   * @param {object} handlers
   * @param {() => Promise<any>} handlers.request Xin lời nhắn mới (``challenge`` | ``locked`` | ``misconfigured``).
   * @param {(code: string) => Promise<any>} handlers.submit Gửi mã 6 số.
   * @param {() => void} [handlers.onOpened] Gọi khi mở được link.
   * @param {() => void} [handlers.onClose] Gọi khi bấm "Đóng" ở màn hình 2.
   * @param {unknown} [handlers.name] Tên người giám hộ (tùy chọn).
   * @param {string} [idPrefix]
   * @returns {{root: HTMLElement, open: () => Promise<void>, destroy: () => void, readonly isOpen: boolean}}
   */
  function mount(container, handlers, idPrefix = "chotto-g") {
    const guardianName = cleanName(handlers.name);
    const root = el("section", "gd");
    root.hidden = true;
    root.setAttribute("aria-labelledby", `${idPrefix}-title`);
    const title = el("h2", "gd-title");
    title.id = `${idPrefix}-title`;
    title.append(document.createTextNode(guardianName ? TEXT.titlePrefix : TEXT.titleDefault));
    if (guardianName) title.append(el("b", "gd-name", guardianName));
    const status = el("p", "gd-status");
    status.id = `${idPrefix}-status`;
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    const body = el("div", "gd-body");
    root.append(title, body);
    container.append(root);

    /** @type {ReturnType<typeof setInterval> | null} */
    let timer = null;
    let busy = false;
    let isOpen = false;
    /** @type {HTMLInputElement | null} */
    let input = null;
    /** @type {HTMLButtonElement | null} */
    let submitBtn = null;
    /** @type {ChallengeView | null} */
    let current = null;
    /** @type {HTMLElement | null} */
    let remind = null;
    /** @type {HTMLElement | null} */
    let lead = null;

    const stopTimer = () => {
      if (timer !== null) clearInterval(timer);
      timer = null;
    };

    /** @param {string} message */
    const say = (message) => {
      status.textContent = message;
    };

    const refreshSubmit = () => {
      if (submitBtn) submitBtn.disabled = busy;
    };

    /** @param {string} message */
    const tell = (message) => {
      if (lead) lead.textContent = message;
    };

    /** Chép lời nhắn hiện tại vào clipboard và báo kết quả bằng chữ. */
    const copyMessage = async (/** @type {boolean} */ again) => {
      if (!current) return;
      const ok = await copyText(current.message, root);
      tell(ok ? (again ? TEXT.copiedAgain : TEXT.copied) : TEXT.copyFailed);
    };

    /** Vẽ lại phần thân theo lời nhắn đang có. */
    const renderChallenge = () => {
      const view = current;
      if (!view) return;
      stopTimer();
      body.replaceChildren();

      lead = el("p", "gd-lead");
      lead.setAttribute("role", "status");
      lead.setAttribute("aria-live", "polite");
      const how = el("p", "gd-how", TEXT.how);
      const again = /** @type {HTMLButtonElement} */ (el("button", "gd-ghost", TEXT.copyAgain));
      again.type = "button";
      again.addEventListener("click", () => copyMessage(true));
      const send = el("div", "gd-send");
      send.append(lead, how, again);

      const form = el("div", "gd-form");
      const codeLabel = el("label", "gd-step", TEXT.codeIntro);
      const field = /** @type {HTMLInputElement} */ (el("input", "gd-code"));
      field.id = `${idPrefix}-code`;
      codeLabel.setAttribute("for", field.id);
      field.type = "text";
      field.inputMode = "numeric";
      field.autocomplete = "one-time-code";
      field.enterKeyHint = "go";
      field.spellcheck = false;
      field.maxLength = 40; // đủ để dán cả câu "Mã của bạn là 123 456"
      field.setAttribute("aria-label", TEXT.codeLabel);
      field.setAttribute("aria-describedby", status.id);
      field.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          sendCode();
        }
      });
      input = field;
      const submit = /** @type {HTMLButtonElement} */ (el("button", "gd-open", TEXT.open));
      submit.type = "button";
      submit.addEventListener("click", () => sendCode());
      submitBtn = submit;
      const trust = el("p", "gd-trust", TEXT.trust);
      form.append(codeLabel, field, submit, status, trust);
      remind = el("p", "gd-remind");
      remind.hidden = true;

      const fallback = buildFallback(view);
      const close = /** @type {HTMLButtonElement} */ (el("button", "gd-close", TEXT.close));
      close.type = "button";
      close.addEventListener("click", () => handlers.onClose?.());
      body.append(send, form, remind, fallback, close);
      refreshSubmit();

      const tick = () => {
        const left = view.expiresAt - Date.now();
        if (left <= 0) {
          showGone(TEXT.gone);
          return;
        }
        if (remind) {
          remind.hidden = left > REMIND_MS;
          if (left <= REMIND_MS) remind.textContent = TEXT.expiresSoon(clock(left));
        }
      };
      tick();
      if (timer === null && current) timer = setInterval(tick, 1000);
    };

    /**
     * Phương án dự phòng thu gọn: đọc mã bằng miệng + hình vuông quét.
     * @param {ChallengeView} view
     * @returns {HTMLElement}
     */
    const buildFallback = (view) => {
      const wrap = el("div", "gd-fallback");
      const toggle = /** @type {HTMLButtonElement} */ (el("button", "gd-more-toggle", TEXT.fallbackToggle));
      toggle.type = "button";
      toggle.setAttribute("aria-expanded", "false");
      const panel = el("div", "gd-fallback-body");
      panel.id = `${idPrefix}-fallback`;
      panel.hidden = true;
      toggle.setAttribute("aria-controls", panel.id);
      toggle.addEventListener("click", () => {
        const open = toggle.getAttribute("aria-expanded") !== "true";
        toggle.setAttribute("aria-expanded", String(open));
        panel.hidden = !open;
      });
      /**
       * @param {string} text
       * @param {string} cap
       * @param {string} cls
       */
      const figure = (text, cap, cls) => {
        const box = el("div", "gd-fig");
        const value = el("div", cls, text);
        value.setAttribute("translate", "no");
        box.append(el("span", "gd-cap", cap), value);
        return box;
      };
      panel.append(
        el("p", "gd-step", TEXT.fallbackIntro),
        figure(view.domain, TEXT.siteCaption, "gd-domain"),
        figure(view.nonceText, TEXT.codeCaption, "gd-nonce"),
      );
      const svg = qrSvg(view.qr);
      if (svg) {
        const qr = el("div", "gd-qr");
        qr.append(svg);
        panel.append(el("p", "gd-step", TEXT.scanIntro), qr);
      }
      panel.append(el("p", "gd-step", TEXT.fallbackOutro));
      wrap.append(toggle, panel);
      return wrap;
    };

    /** @param {string} message */
    const showGone = (message) => {
      stopTimer();
      current = null;
      input = null;
      submitBtn = null;
      body.replaceChildren();
      const again = /** @type {HTMLButtonElement} */ (el("button", "gd-open", TEXT.renew));
      again.type = "button";
      again.addEventListener("click", () => load());
      body.append(status, again);
      say(message);
      again.focus();
    };

    /** @param {number} until */
    const showLocked = (until) => {
      stopTimer();
      current = null;
      input = null;
      submitBtn = null;
      body.replaceChildren();
      const line = el("p", "gd-lock");
      const again = /** @type {HTMLButtonElement} */ (el("button", "gd-open", TEXT.renew));
      again.type = "button";
      again.disabled = true;
      again.addEventListener("click", () => load());
      body.append(status, line, again);
      const tick = () => {
        const left = until - Date.now();
        if (left <= 0) {
          stopTimer();
          line.textContent = TEXT.lockedEnd;
          again.disabled = false;
          say(TEXT.lockedEnd);
          again.focus();
          return;
        }
        line.textContent = TEXT.lockedIn(clock(left));
      };
      tick();
      say(TEXT.locked);
      if (timer === null && until - Date.now() > 0) timer = setInterval(tick, 1000);
    };

    /** Xin lời nhắn mới từ service worker, rồi tự chép vào clipboard. */
    async function load() {
      if (busy) return;
      busy = true;
      say(TEXT.loading);
      body.replaceChildren(status);
      try {
        const answer = await handlers.request();
        if (answer.state === "challenge") {
          current = answer;
          say("");
          renderChallenge();
          await copyMessage(false);
          input?.focus();
        } else if (answer.state === "locked") {
          showLocked(Number(answer.until));
        } else {
          stopTimer();
          body.replaceChildren(status);
          say(TEXT.misconfigured);
        }
      } catch (error) {
        console.warn("CHOTTO: không tạo được lời nhắn", error);
        showGone(TEXT.unavailable);
      } finally {
        busy = false;
        refreshSubmit();
      }
    }

    /** Gửi mã đang nhập. */
    async function sendCode() {
      if (busy || !current || !input) return;
      const code = normalizeCode(input.value);
      if (code === null) {
        say(TEXT.format);
        input.focus();
        return;
      }
      busy = true;
      refreshSubmit();
      try {
        const answer = await handlers.submit(code);
        if (answer.ok) {
          stopTimer();
          say(TEXT.ok);
          handlers.onOpened?.();
          return;
        }
        if (input) input.value = "";
        switch (answer.reason) {
          case "wrong":
            say(TEXT.wrong(Number(answer.attemptsLeft ?? 0)));
            if (current) current.attemptsLeft = Number(answer.attemptsLeft ?? 0);
            input?.focus();
            break;
          case "format":
            say(TEXT.format);
            input?.focus();
            break;
          case "destroyed":
            if (answer.lockedUntil) showLocked(Number(answer.lockedUntil));
            else showGone(TEXT.destroyed);
            break;
          case "locked":
            showLocked(Number(answer.lockedUntil));
            break;
          case "mismatch":
            showGone(TEXT.mismatch);
            break;
          case "misconfigured":
            stopTimer();
            body.replaceChildren(status);
            say(TEXT.misconfigured);
            break;
          default:
            showGone(TEXT.gone);
        }
      } catch (error) {
        console.warn("CHOTTO: lỗi gửi mã", error);
        say(TEXT.unavailable);
      } finally {
        busy = false;
        refreshSubmit();
      }
    }

    return {
      root,
      get isOpen() {
        return isOpen;
      },
      async open() {
        if (isOpen) {
          (input ?? root).focus?.();
          return;
        }
        isOpen = true;
        root.hidden = false;
        await load();
      },
      destroy() {
        stopTimer();
      },
    };
  }

  /** @type {any} */ (globalThis).ChottoGuardianUI = Object.freeze({
    mount, blockView, arrange, setStep, askText, cleanName, normalizeCode, TEXT,
  });
})();
