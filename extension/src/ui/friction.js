// @ts-check
/**
 * Màn hình "Khoan đã!" (Intentional Friction) dùng chung cho content script trên Zalo Web và trang cảnh báo.
 * Giao diện cùng phong cách với bản Desktop ("luxury": nền đen ấm, vàng đồng, chữ serif).
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
  const RING = 50.27;
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
      --bg: #0c0a08; --surface: #161310; --surface2: #1f1b16; --ink: #f4efe7; --muted: #a89f92; --faint: #6f675d;
      --line: rgba(244,239,231,.1); --line-strong: rgba(244,239,231,.2);
      --accent: #c9a45a; --accent-ink: #17110a; --accent-hi: #d8b874; --accent-soft: rgba(201,164,90,.12);
      --danger: #e5484d; --danger-field: #230c0b; --danger-ink: #ff9c8f; --danger-chip: rgba(229,72,77,.16);
      --warn: #e0a84a; --warn-field: #221906; --warn-ink: #f0c47a; --warn-chip: rgba(224,168,74,.16);
      --ok: #7fc8a0; --ok-chip: rgba(127,200,160,.14);
      --serif: "Newsreader", "Iowan Old Style", "Palatino Linotype", Georgia, "Times New Roman", serif;
      --sans: "Onest", "Segoe UI", system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, sans-serif;
      --ease: cubic-bezier(.2,.7,.2,1);
      width: min(1040px, calc(100vw - 48px)); max-height: calc(100vh - 32px); overflow: hidden; margin: auto; padding: 0;
      border: 0; border-radius: 20px; background: var(--bg); color: var(--ink);
      font: 16px/1.6 var(--sans); -webkit-font-smoothing: antialiased;
      box-shadow: 0 0 0 1px var(--line), 0 32px 80px rgba(0,0,0,.65);
      animation: rise .35s var(--ease) both;
    }
    dialog[open] { display: flex; flex-direction: column; }
    .scroll { flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain; }
    .top, .verdict, .actionbar { flex: none; }
    dialog::backdrop { background: rgba(6,5,4,.78); backdrop-filter: blur(3px); }
    .scroll::-webkit-scrollbar { width: 10px; }
    .scroll::-webkit-scrollbar-thumb { background: rgba(244,239,231,.16); border-radius: 999px; border: 3px solid var(--bg); }
    @keyframes rise { from { opacity: 0; transform: translateY(10px) scale(.99); } }
    @keyframes pulse { 50% { opacity: .3; } }

    .top { display: flex; align-items: center; gap: 10px; padding: 14px 24px 0; font-size: 13px; color: var(--muted); }
    .mark { width: 26px; height: 26px; display: inline-block; flex: none; background: center / contain no-repeat; }

    .verdict { margin-top: 8px; padding: 22px 32px 28px; display: grid; grid-template-columns: 1fr 200px; gap: 24px; align-items: end; }
    .verdict[data-level="HIGH"], .verdict[data-level="BLOCKED"] { background: var(--danger-field); }
    .verdict[data-level="WARN"] { background: var(--warn-field); }
    h1 { margin: 0; font: 400 34px/1.08 var(--serif); letter-spacing: -.02em; }
    h1 .k { display: block; font-size: 46px; line-height: 1.05; }
    .verdict[data-level="HIGH"] .k, .verdict[data-level="BLOCKED"] .k { color: var(--danger-ink); }
    .verdict[data-level="WARN"] .k { color: var(--warn-ink); }
    .verdict p { margin: 12px 0 0; font-size: 16px; color: var(--ink); max-width: 44ch; }
    .meter { text-align: right; }
    .meter b { display: block; font: 300 64px/.85 var(--serif); letter-spacing: -.04em; }
    .meter .lbl { display: block; margin-top: 8px; font-size: 12px; color: var(--muted); }
    .track { margin-top: 14px; height: 4px; display: grid; grid-template-columns: 30fr 30fr 40fr; gap: 4px; }
    .track span { border-radius: 2px; background: rgba(244,239,231,.12); overflow: hidden; }
    .track i { display: block; height: 100%; transform-origin: left; transform: scaleX(0); transition: transform .8s var(--ease); }
    .verdict[data-level="HIGH"] .track i, .verdict[data-level="BLOCKED"] .track i { background: var(--danger); }
    .verdict[data-level="WARN"] .track i { background: var(--warn); }
    .scale { display: grid; grid-template-columns: 30fr 30fr 40fr; gap: 4px; margin-top: 6px; font-size: 11px; color: var(--muted); text-align: left; white-space: nowrap; }
    .scale span:nth-child(3) { text-align: right; }

    .wbody { padding: 22px 32px 8px; display: grid; gap: 14px; }
    .card { background: var(--surface); border-radius: 18px; padding: 24px 26px; box-shadow: inset 0 0 0 1px var(--line); }
    .h2 { margin: 0 0 16px; font: 400 22px/1.2 var(--serif); letter-spacing: -.01em; }
    .parts { display: flex; flex-wrap: wrap; align-items: flex-start; row-gap: 14px; }
    .part { display: flex; flex-direction: column; min-width: 0; }
    .part code { font: 500 19px/1.25 var(--sans); letter-spacing: -.015em; padding: 6px 2px; border-radius: 8px; word-break: break-all; }
    .part small { margin-top: 8px; padding: 0 2px; font-size: 12px; font-weight: 500; color: var(--muted); white-space: nowrap; }
    .part small::before { content: ""; display: block; height: 2px; border-radius: 1px; margin-bottom: 6px; background: currentColor; opacity: .6; }
    .part.dim code { color: var(--faint); }
    .part.decoy code { color: var(--faint); text-decoration: line-through; text-decoration-thickness: 2px; text-decoration-color: rgba(229,72,77,.6); }
    .part.decoy small { color: var(--danger-ink); }
    .part.real code, .part.warnpart code { padding: 6px 12px; margin: 0 5px; font-weight: 700; }
    .part.real small, .part.warnpart small { margin-left: 5px; margin-right: 5px; }
    .part.real code { background: var(--danger-chip); color: var(--danger-ink); }
    .part.real small { color: var(--danger-ink); }
    .part.warnpart code { background: var(--warn-chip); color: var(--warn-ink); }
    .part.warnpart small { color: var(--warn-ink); }
    .full { margin: 16px 0 0; font-size: 12px; color: var(--faint); word-break: break-all; max-height: 72px; overflow: auto; }

    .two { display: grid; grid-template-columns: 1.15fr 1fr; gap: 14px; }
    .reasons ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; }
    .reasons li { display: grid; grid-template-columns: 12px 1fr; gap: 12px; font-size: 15px; }
    .reasons .dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 9px; background: var(--danger); }
    .reasons[data-level="WARN"] .dot { background: var(--warn); }
    .reasons .src { margin: 18px 0 0; font-size: 12px; color: var(--muted); }
    .advice { background: var(--accent-soft); box-shadow: none; }
    .advice .h2 { color: var(--accent-hi); }
    .advice p { margin: 0; font-size: 15px; }

    .note { min-height: 20px; padding: 10px 32px 0; color: var(--danger-ink); font-size: 13px; }
    .actionbar { padding: 16px 32px 24px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; border-top: 1px solid var(--line); margin-top: 6px; }
    .hint { margin-right: auto; font-size: 13px; color: var(--muted); }
    button { font: inherit; color: inherit; border: 0; background: none; cursor: pointer; }
    .back, .proceed { white-space: nowrap; height: 48px; padding: 0 26px; border-radius: 999px; font-size: 15px; font-weight: 600; display: inline-flex;
      align-items: center; justify-content: center; gap: 10px; transition: transform .15s var(--ease), background .2s, box-shadow .2s, color .2s; }
    .back:active, .proceed:active { transform: translateY(1px) scale(.985); }
    .back { background: var(--accent); color: var(--accent-ink); }
    .back:hover { background: var(--accent-hi); transform: translateY(-1px); }
    .back:focus-visible, .proceed:focus-visible { outline: 2px solid var(--accent-hi); outline-offset: 3px; }
    .proceed { box-shadow: inset 0 0 0 1px var(--line-strong); color: var(--ink); }
    .proceed[aria-disabled="true"] { color: var(--muted); cursor: not-allowed; }
    .proceed[aria-disabled="false"]:hover { box-shadow: inset 0 0 0 1px var(--ink); transform: translateY(-1px); }
    .ring { width: 20px; height: 20px; transform: rotate(-90deg); }
    .ring circle { fill: none; stroke-width: 2; }
    .ring .bgc { stroke: var(--line-strong); }
    .ring .fg { stroke: var(--accent); stroke-linecap: round; }
    .proceed[aria-disabled="false"] .ring { display: none; }

    @media (max-height: 820px) {
      .verdict { padding: 14px 32px 18px; margin-top: 4px; }
      h1 { font-size: 28px; } h1 .k { font-size: 38px; }
      .verdict p { margin-top: 6px; font-size: 15px; }
      .meter b { font-size: 48px; }
      .wbody { padding-top: 16px; gap: 12px; } .card { padding: 18px 22px; } .h2 { margin-bottom: 12px; font-size: 20px; }
      .actionbar { padding: 12px 32px 16px; } .note { padding-top: 6px; }
    }
    @media (max-width: 640px) {
      .verdict { grid-template-columns: 1fr; padding: 20px 22px 24px; }
      .meter { text-align: left; }
      .wbody { padding: 18px 20px 6px; } .two { grid-template-columns: 1fr; }
      .actionbar { padding: 14px 20px 20px; } .actionbar button { flex: 1; } .hint { width: 100%; }
      .note { padding: 8px 20px 0; }
    }
    @media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
    .toast { position: fixed; top: 16px; right: 16px; z-index: 2147483647; background: #0c0a08; color: #f4efe7;
      border: 1px solid #c9a45a; border-radius: 999px; padding: 10px 18px;
      font: 13px/1.4 "Onest", "Segoe UI", system-ui, -apple-system, Roboto, sans-serif; box-shadow: 0 8px 24px rgba(0,0,0,.4); }
  `;

  /**
   * Thay ký tự điều khiển/vô hình/đảo chiều bằng U+FFFD (phòng khi dữ liệu chưa được lọc).
   * @param {unknown} text
   * @returns {string}
   */
  function clean(text) {
    return String(text ?? "").replace(/[\p{Cc}\p{Cf}\p{Co}\p{Cs}\p{Zl}\p{Zp}]/gu, "�");
  }

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
   * Phần tử SVG (tạo bằng DOM, không innerHTML).
   * @param {string} tag
   * @param {Record<string, string>} attrs
   * @returns {SVGElement}
   */
  function svg(tag, attrs) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
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
    style.textContent = STYLE;
    root.append(style);
    parent.append(host);
    return { host, root };
  }

  /**
   * Tách "Khoan đã! Liên kết này đáng ngờ" thành ["Khoan đã!", "Liên kết này đáng ngờ"].
   * @param {string} title
   * @returns {[string, string]}
   */
  function splitTitle(title) {
    const at = title.indexOf("! ");
    return at > 0 ? [title.slice(0, at + 1), title.slice(at + 2)] : ["Khoan đã!", title];
  }

  /**
   * @typedef {object} FrictionView
   * @property {string} level
   * @property {string} title
   * @property {string} domainLine
   * @property {string} url
   * @property {number} score
   * @property {string} tierText
   * @property {string[]} reasons
   * @property {string} advice
   * @property {{text: string, kind: string, label: string}[]} [parts]
   */

  /**
   * Hiện màn hình friction.
   * @param {object} options
   * @param {FrictionView} options.view Nội dung đã chuẩn bị bởi service worker.
   * @param {number} options.lockMs Thời gian khóa nút "vẫn mở".
   * @param {(choice: "proceed" | "back", trusted: boolean) => Promise<{ok: boolean, reason?: string}>} options.decide
   * @param {Element} [options.parent] Nơi gắn (mặc định ``document.documentElement``).
   * @returns {{close: () => void}}
   */
  function show({ view, lockMs, decide, parent }) {
    const { host, root } = mountHost(parent ?? document.documentElement);
    const level = ["WARN", "HIGH", "BLOCKED"].includes(view.level) ? view.level : "WARN";
    const dialog = /** @type {HTMLDialogElement} */ (el("dialog"));
    dialog.setAttribute("aria-labelledby", "chotto-title");

    // ---- đầu trang + kết luận + thanh điểm ----
    const top = el("div", "top");
    const mark = el("span", "mark");
    mark.setAttribute("aria-hidden", "true");
    const icon = /** @type {any} */ (globalThis).CHOTTO_ICON;
    if (typeof icon === "string" && icon.startsWith("data:image/png;base64,")) mark.style.backgroundImage = `url("${icon}")`;
    top.append(mark, el("span", "", "CHOTTO · liên kết mở từ Zalo"));

    const verdict = el("section", "verdict");
    verdict.dataset.level = level;
    const [lead, rest] = splitTitle(clean(view.title));
    const title = el("h1");
    title.id = "chotto-title";
    title.append(el("span", "k", lead), document.createTextNode(` ${rest}`));
    const left = el("div");
    left.append(title, el("p", "", clean(view.domainLine)));
    const meter = el("div", "meter");
    const score = Math.max(0, Math.min(100, Number(view.score) || 0));
    const track = el("div", "track");
    track.setAttribute("aria-hidden", "true");
    const fills = [0, 1, 2].map(() => el("i"));
    for (const fill of fills) {
      const cell = el("span");
      cell.append(fill);
      track.append(cell);
    }
    const scale = el("div", "scale");
    scale.setAttribute("aria-hidden", "true");
    scale.append(el("span", "", "An toàn"), el("span", "", "Đáng ngờ"), el("span", "", "Nguy hiểm"));
    meter.append(el("b", "", String(score)), el("span", "lbl", "điểm rủi ro trên 100"), track, scale);
    verdict.append(left, meter);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      [[0, 30], [30, 60], [60, 100]].forEach(([from, to], i) => {
        fills[i].style.transform = `scaleX(${Math.max(0, Math.min(1, (score - from) / (to - from)))})`;
      });
    }));

    // ---- đường link thật sự đi đâu ----
    const wbody = el("div", "wbody");
    const anatomy = el("section", "card");
    anatomy.append(el("h2", "h2", "Liên kết này thật sự dẫn tới đâu"));
    const parts = el("div", "parts");
    const shownParts = Array.isArray(view.parts) && view.parts.length
      ? view.parts
      : [{ text: view.url, kind: "dim", label: "" }];
    for (const piece of shownParts) {
      const kind = ["dim", "decoy", "real", "warnpart"].includes(piece.kind) ? piece.kind : "dim";
      const part = el("span", `part ${kind}`);
      part.append(el("code", "", clean(piece.text)));
      if (piece.label) part.append(el("small", "", clean(piece.label)));
      parts.append(part);
    }
    anatomy.append(parts, el("p", "full", clean(view.url)));
    wbody.append(anatomy);

    // ---- vì sao + nên làm gì ----
    const two = el("div", "two");
    const why = el("section", "card reasons");
    why.dataset.level = level;
    why.append(el("h2", "h2", level === "WARN" ? "Vì sao CHOTTO nghi ngờ" : "Vì sao CHOTTO chặn"));
    if (view.reasons.length) {
      const list = el("ul");
      for (const reason of view.reasons) {
        const item = el("li");
        item.append(el("i", "dot"), el("div", "", clean(reason)));
        list.append(item);
      }
      why.append(list);
    }
    why.append(el("p", "src", `Phát hiện ở: ${clean(view.tierText)}`));
    two.append(why);
    const adviceText = clean(view.advice);
    const advice = el("section", "card advice");
    advice.append(el("h2", "h2", "Bạn nên làm gì"),
      el("p", "", adviceText || "Đừng đăng nhập hay nhập mã OTP, mật khẩu, CCCD trên trang này. Nếu nghi ngờ, hãy hỏi người thân hoặc gọi số hotline chính thức."));
    two.append(advice);
    wbody.append(two);

    // ---- thanh hành động ----
    const note = el("div", "note");
    note.setAttribute("role", "status");
    const actions = el("div", "actionbar");
    const back = /** @type {HTMLButtonElement} */ (el("button", "back", "Đóng, không mở"));
    back.type = "button";
    back.autofocus = true;
    const proceed = /** @type {HTMLButtonElement} */ (el("button", "proceed"));
    proceed.type = "button";
    proceed.tabIndex = -1;
    proceed.setAttribute("aria-disabled", "true");
    const ring = svg("svg", { class: "ring", viewBox: "0 0 20 20", "aria-hidden": "true" });
    ring.append(svg("circle", { class: "bgc", cx: "10", cy: "10", r: "8" }),
      svg("circle", { class: "fg", cx: "10", cy: "10", r: "8", "stroke-dasharray": String(RING), "stroke-dashoffset": String(RING) }));
    const ringFg = /** @type {SVGElement} */ (ring.querySelector(".fg"));
    const proceedLabel = el("span");
    proceed.append(ring, proceedLabel);
    actions.append(el("span", "hint", "Nhấn Esc để đóng"), proceed, back);
    const scroller = el("div", "scroll");
    scroller.append(wbody, note);
    dialog.append(top, verdict, scroller, actions);
    root.append(dialog);

    const startedAt = performance.now();
    const unlockAt = startedAt + Math.max(0, lockMs);
    let pointerDownAt = -Infinity;
    let busy = false;
    let closed = false;

    const render = () => {
      const left = unlockAt - performance.now();
      const remaining = Math.ceil(left / 1000);
      if (remaining > 0) {
        proceedLabel.textContent = `Tôi hiểu rủi ro, vẫn mở (${remaining})`;
        proceed.setAttribute("aria-disabled", "true");
        ringFg.setAttribute("stroke-dashoffset", String(RING * Math.max(0, left / Math.max(1, unlockAt - startedAt))));
      } else {
        proceedLabel.textContent = "Tôi hiểu rủi ro, vẫn mở";
        proceed.setAttribute("aria-disabled", "false");
      }
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
        else note.textContent = /** @type {Record<string, string>} */ (REASON_TEXT)[answer.reason ?? ""] ?? REASON_TEXT.unavailable;
      } catch (error) {
        console.error("CHOTTO: lỗi gửi quyết định", error);
        if (choice === "back") close();
        else note.textContent = REASON_TEXT.unavailable;
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
        note.textContent = REASON_TEXT.locked;
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
