// @ts-check
/**
 * Màn hình "Xin phép người giám hộ" (Guardian mode): tên miền nổi bật, mã thử thách lớn + mã QR, 6 ô nhập mã mở khóa
 * (tự nhảy ô, dán được), thông báo lỗi, số lần còn lại, trạng thái bị khóa tạm.
 *
 * Phần này CHỈ là giao diện: mọi quyết định (mã đúng/sai, khóa, hết hạn) do service worker đưa ra.
 * Script thường (không phải module) vì content script không nạp được ES module; gắn ``globalThis.ChottoGuardianUI``.
 * Mọi chuỗi gán bằng ``textContent``; mã QR dựng bằng DOM SVG. Truy cập: nhãn cho từng ô, ``aria-live``, bàn phím đầy đủ,
 * không phụ thuộc màu (mỗi trạng thái đều có chữ), tôn trọng ``prefers-reduced-motion`` (không có hoạt ảnh).
 */
(() => {
  if (/** @type {any} */ (globalThis).ChottoGuardianUI) return;

  const SVG_NS = "http://www.w3.org/2000/svg";
  const DIGITS = 6;
  const TEXT = Object.freeze({
    ask: "Xin phép người giám hộ",
    title: "Cần người giám hộ cho phép",
    intro: "Link này nguy hiểm nên CHOTTO không cho mở nếu người giám hộ của bạn chưa đồng ý.",
    warning: "Chỉ người giám hộ của bạn mới đưa mã này. Ai gọi điện xin mã thử thách là kẻ lừa đảo.",
    step1: "1. Đưa cho người giám hộ (người bạn tự liên lạc) tên miền và mã thử thách này, hoặc cho họ quét mã QR:",
    step2: "2. Nhập mã mở khóa 6 số mà họ đưa lại:",
    domainCaption: "Trang sẽ mở",
    challengeCaption: "Mã thử thách",
    qrLabel: "Mã QR chứa tên miền và mã thử thách",
    digitsLabel: "Mã mở khóa 6 số",
    digit: (/** @type {number} */ n) => `Chữ số ${n} trên ${DIGITS}`,
    open: "Mở link",
    renew: "Tạo thử thách mới",
    loading: "Đang tạo thử thách…",
    expires: (/** @type {string} */ t) => `Thử thách hết hạn sau ${t}.`,
    wrong: (/** @type {number} */ n) => `Mã chưa đúng. Còn ${n} lần thử.`,
    format: "Mã gồm đúng 6 chữ số.",
    attempts: (/** @type {number} */ n) => `Còn ${n} lần thử.`,
    locked: "Đã nhập sai quá nhiều lần.",
    lockedIn: (/** @type {string} */ t) => `Thử lại sau ${t}.`,
    lockedEnd: "Hết thời gian khóa. Bạn có thể tạo thử thách mới.",
    gone: "Thử thách đã hết hạn hoặc đã bị hủy. Hãy tạo thử thách mới.",
    destroyed: "Quá 5 lần sai nên thử thách đã bị hủy.",
    mismatch: "Thử thách này không thuộc link đang mở. Hãy tạo thử thách mới.",
    misconfigured: "Chế độ người giám hộ chưa được cài đúng nên link này không thể mở. Hãy liên hệ người giám hộ của bạn.",
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
   * Mã QR dạng SVG (nền trắng, điểm đen, viền yên tĩnh 4 ô) từ thư viện qrcode-generator đã đóng gói.
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
      svg.setAttribute("aria-label", TEXT.qrLabel);
      const bg = document.createElementNS(SVG_NS, "rect");
      bg.setAttribute("width", String(size));
      bg.setAttribute("height", String(size));
      bg.setAttribute("fill", "#ffffff");
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", d);
      path.setAttribute("fill", "#000000");
      // .sh svg (shield.css) vẽ biểu tượng bằng nét viền; mã QR phải là ô đặc, không viền.
      bg.style.stroke = path.style.stroke = "none";
      svg.append(bg, path);
      return svg;
    } catch {
      return null;
    }
  }

  /**
   * @typedef {object} ChallengeView
   * @property {"challenge"} state
   * @property {string} domain
   * @property {string} nonceText
   * @property {string} qr
   * @property {number} expiresAt
   * @property {number} attemptsLeft
   */

  /**
   * Dựng khung xin phép vào ``container``.
   * @param {Element} container
   * @param {object} handlers
   * @param {() => Promise<any>} handlers.request Xin thử thách mới (``challenge`` | ``locked`` | ``misconfigured``).
   * @param {(code: string) => Promise<any>} handlers.submit Gửi mã 6 số.
   * @param {() => void} [handlers.onOpened] Gọi khi mở được link.
   * @param {string} [idPrefix]
   * @returns {{root: HTMLElement, open: () => Promise<void>, destroy: () => void, readonly isOpen: boolean}}
   */
  function mount(container, handlers, idPrefix = "chotto-g") {
    const root = el("section", "gd");
    root.hidden = true;
    root.setAttribute("aria-labelledby", `${idPrefix}-title`);
    const title = el("h2", "gd-title", TEXT.title);
    title.id = `${idPrefix}-title`;
    const intro = el("p", "gd-intro", TEXT.intro);
    const warning = el("p", "gd-warn", TEXT.warning);
    warning.setAttribute("role", "note");
    const body = el("div", "gd-body");
    const status = el("p", "gd-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    root.append(title, intro, warning, status, body);
    container.append(root);

    /** @type {ReturnType<typeof setInterval> | null} */
    let timer = null;
    let busy = false;
    let isOpen = false;
    /** @type {HTMLInputElement[]} */
    let boxes = [];
    /** @type {HTMLButtonElement | null} */
    let submitBtn = null;
    /** @type {ChallengeView | null} */
    let current = null;
    /** @type {number} */
    let lockedUntil = 0;
    /** @type {HTMLElement | null} */
    let countdown = null;

    const stopTimer = () => {
      if (timer !== null) clearInterval(timer);
      timer = null;
    };

    /** @param {string} message */
    const say = (message) => {
      status.textContent = message;
    };

    const code = () => boxes.map((b) => b.value).join("");
    const refreshSubmit = () => {
      if (submitBtn) submitBtn.disabled = busy || code().length !== DIGITS;
    };

    /**
     * Phân phối chữ số vào các ô từ ``from``.
     * @param {string} digits
     * @param {number} from
     */
    const fill = (digits, from) => {
      let i = from;
      for (const ch of digits.replace(/\D/g, "")) {
        if (i >= DIGITS) break;
        boxes[i].value = ch;
        i += 1;
      }
      boxes[Math.min(i, DIGITS - 1)].focus();
      refreshSubmit();
    };

    /** @returns {HTMLElement} Hàng 6 ô nhập. */
    const buildInputs = () => {
      const group = el("div", "gd-digits");
      group.setAttribute("role", "group");
      const label = el("span", "gd-cap", TEXT.digitsLabel);
      label.id = `${idPrefix}-digits`;
      group.setAttribute("aria-labelledby", label.id);
      boxes = [];
      const row = el("div", "gd-row");
      for (let i = 0; i < DIGITS; i++) {
        const box = /** @type {HTMLInputElement} */ (el("input", "gd-digit"));
        box.type = "text";
        box.inputMode = "numeric";
        box.autocomplete = "off";
        box.maxLength = 1;
        box.setAttribute("pattern", "[0-9]");
        box.setAttribute("aria-label", TEXT.digit(i + 1));
        box.spellcheck = false;
        box.addEventListener("input", () => {
          const digits = box.value.replace(/\D/g, "");
          if (digits.length > 1) {
            box.value = "";
            fill(digits, i);
            return;
          }
          box.value = digits;
          if (digits && i < DIGITS - 1) boxes[i + 1].focus();
          refreshSubmit();
        });
        box.addEventListener("keydown", (event) => {
          if (event.key === "Backspace" && !box.value && i > 0) {
            boxes[i - 1].value = "";
            boxes[i - 1].focus();
            refreshSubmit();
            event.preventDefault();
          } else if (event.key === "ArrowLeft" && i > 0) {
            boxes[i - 1].focus();
            event.preventDefault();
          } else if (event.key === "ArrowRight" && i < DIGITS - 1) {
            boxes[i + 1].focus();
            event.preventDefault();
          } else if (event.key === "Enter") {
            event.preventDefault();
            send();
          }
        });
        box.addEventListener("paste", (event) => {
          event.preventDefault();
          fill(event.clipboardData?.getData("text") ?? "", 0);
        });
        box.addEventListener("focus", () => box.select());
        boxes.push(box);
        row.append(box);
      }
      group.append(label, row);
      return group;
    };

    /**
     * @param {string} text
     * @param {string} cap
     * @param {string} cls
     * @returns {HTMLElement}
     */
    const figure = (text, cap, cls) => {
      const wrap = el("div", "gd-fig");
      const c = el("span", "gd-cap", cap);
      const v = el("div", cls, text);
      v.setAttribute("translate", "no");
      wrap.append(c, v);
      return wrap;
    };

    /** Vẽ lại phần thân theo thử thách đang có. */
    const renderChallenge = () => {
      const view = current;
      if (!view) return;
      stopTimer();
      body.replaceChildren();
      const steps = el("p", "gd-step", TEXT.step1);
      const share = el("div", "gd-share");
      const left = el("div", "gd-left");
      left.append(figure(view.domain, TEXT.domainCaption, "gd-domain"), figure(view.nonceText, TEXT.challengeCaption, "gd-nonce"));
      share.append(left);
      const svg = qrSvg(view.qr);
      if (svg) {
        const qr = el("div", "gd-qr");
        qr.append(svg);
        share.append(qr);
      }
      countdown = el("p", "gd-count");
      const form = el("div", "gd-form");
      const step2 = el("p", "gd-step", TEXT.step2);
      const submit = /** @type {HTMLButtonElement} */ (el("button", "gd-open", TEXT.open));
      submit.type = "button";
      submit.addEventListener("click", () => send());
      submitBtn = submit;
      form.append(step2, buildInputs(), submit);
      body.append(steps, share, countdown, form);
      refreshSubmit();
      const tick = () => {
        const left = view.expiresAt - Date.now();
        if (left <= 0) {
          showGone(TEXT.gone);
          return;
        }
        if (countdown) countdown.textContent = TEXT.expires(clock(left));
      };
      tick();
      timer = setInterval(tick, 1000);
    };

    /** @param {string} message */
    const showGone = (message) => {
      stopTimer();
      current = null;
      body.replaceChildren();
      const again = /** @type {HTMLButtonElement} */ (el("button", "gd-open", TEXT.renew));
      again.type = "button";
      again.addEventListener("click", () => load());
      body.append(again);
      say(message);
      again.focus();
    };

    /** @param {number} until */
    const showLocked = (until) => {
      stopTimer();
      current = null;
      lockedUntil = until;
      body.replaceChildren();
      const line = el("p", "gd-lock");
      const again = /** @type {HTMLButtonElement} */ (el("button", "gd-open", TEXT.renew));
      again.type = "button";
      again.disabled = true;
      again.addEventListener("click", () => load());
      body.append(line, again);
      const tick = () => {
        const left = lockedUntil - Date.now();
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
      if (timer === null && lockedUntil - Date.now() > 0) timer = setInterval(tick, 1000);
    };

    /** Xin thử thách mới từ service worker. */
    async function load() {
      if (busy) return;
      busy = true;
      say(TEXT.loading);
      body.replaceChildren();
      try {
        const answer = await handlers.request();
        if (answer.state === "challenge") {
          current = answer;
          say("");
          renderChallenge();
          boxes[0]?.focus();
        } else if (answer.state === "locked") {
          showLocked(Number(answer.until));
        } else {
          stopTimer();
          body.replaceChildren();
          say(TEXT.misconfigured);
        }
      } catch (error) {
        console.warn("CHOTTO: không xin được thử thách", error);
        showGone(TEXT.unavailable);
      } finally {
        busy = false;
        refreshSubmit();
      }
    }

    /** Gửi mã đang nhập. */
    async function send() {
      if (busy || !current || code().length !== DIGITS) {
        if (!busy && current) say(TEXT.format);
        return;
      }
      busy = true;
      refreshSubmit();
      try {
        const answer = await handlers.submit(code());
        if (answer.ok) {
          stopTimer();
          say(TEXT.ok);
          handlers.onOpened?.();
          return;
        }
        for (const box of boxes) box.value = "";
        switch (answer.reason) {
          case "wrong":
            say(TEXT.wrong(Number(answer.attemptsLeft ?? 0)));
            if (current) current.attemptsLeft = Number(answer.attemptsLeft ?? 0);
            boxes[0]?.focus();
            break;
          case "format":
            say(TEXT.format);
            boxes[0]?.focus();
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
            body.replaceChildren();
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
          (boxes[0] ?? root).focus?.();
          return;
        }
        isOpen = true;
        root.hidden = false;
        root.scrollIntoView?.({ block: "nearest" });
        await load();
      },
      destroy() {
        stopTimer();
      },
    };
  }

  /** @type {any} */ (globalThis).ChottoGuardianUI = Object.freeze({ mount, TEXT });
})();
