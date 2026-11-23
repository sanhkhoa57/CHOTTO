// @ts-check
/**
 * Dựng màn hình cảnh báo "Khoan đã!" (hiển thị lũy tiến) từ view model dùng chung (``chotto/shield.py`` /
 * ``platforms/extension/src/view.js``). MỘT nguồn cho cả Desktop và tiện ích: ``tools/sync_extension_data.py`` chép file này
 * sang ``platforms/extension/src/ui/shield.js``.
 *
 * Mặc định chỉ có: (a) một câu kết luận, (b) tên miền thật làm nổi bật, (c) hành động. Mọi thứ khác nằm trong "Xem vì sao".
 * File là script thường (content script không nạp được ES module), gắn ``globalThis.ChottoShield``.
 * Mọi chuỗi đều gán bằng ``textContent``; không bao giờ dùng innerHTML với dữ liệu.
 */
(() => {
  if (/** @type {any} */ (globalThis).ChottoShield) return;

  const SVG_NS = "http://www.w3.org/2000/svg";
  const RING = 2 * Math.PI * 9;
  /** @type {Record<string, string>} */
  const ICONS = {
    warn: "M12 3.5 22 20.5H2z M12 10v4.5 M12 17.4h.01",
    high: "M8.2 3h7.6L21 8.2v7.6L15.8 21H8.2L3 15.8V8.2z M12 7.5v5.5 M12 16.5h.01",
    blocked: "M5 11h14v9H5z M7.5 11V8a4.5 4.5 0 0 1 9 0v3 M12 14.5v2.5",
    alert: "M12 7.5v5.5 M12 16.6h.01 M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z",
    shield: "M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6z M8.5 12l2.5 2.5 4.5-5",
    badge: "M3 6h18v12H3z M7 12.5a2 2 0 1 0 4 0 2 2 0 0 0-4 0 M14 10h4 M14 14h3",
    eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z M9 12a3 3 0 1 0 6 0 3 3 0 0 0-6 0",
    tag: "M3 3h8l10 10-8 8L3 11z M7.5 7.5h.01",
    shuffle: "M3 7h4l10 10h4 M3 17h4l3-3 M14 10l3-3h4 M18 4l3 3-3 3 M18 14l3 3-3 3",
    server: "M4 4h16v6H4z M4 14h16v6H4z M8 7h.01 M8 17h.01",
    route: "M6 4v8a4 4 0 0 0 4 4h8 M15 13l3 3-3 3",
    lock: "M5 11h14v9H5z M7.5 11V8a4.5 4.5 0 0 1 9 0v3",
    link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1 M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
    clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z M12 7v5l3 2",
    check: "M5 12.5l4.5 4.5L19 7.5",
    copy: "M9 9h11v11H9z M5 15V4h11",
    chat: "M4 5h16v11H9l-5 4z",
    chevron: "M6 9l6 6 6-6",
    back: "M15 5l-7 7 7 7",
  };

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
   * Biểu tượng SVG dựng bằng DOM. Tên lạ rơi về dấu chấm than trong vòng tròn.
   * @param {string} name
   * @returns {SVGElement}
   */
  function icon(name) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", Object.prototype.hasOwnProperty.call(ICONS, name) ? ICONS[name] : ICONS.alert);
    svg.append(path);
    return svg;
  }

  /**
   * Thay ký tự điều khiển/vô hình/đảo chiều bằng U+FFFD (phòng khi dữ liệu chưa được lọc).
   * @param {unknown} text
   * @returns {string}
   */
  function clean(text) {
    return String(text ?? "").replace(/[\p{Cc}\p{Cf}\p{Co}\p{Cs}\p{Zl}\p{Zp}]/gu, "�");
  }

  /**
   * Chép chữ vào clipboard (API hiện đại, rơi về ``execCommand`` khi trang không cho phép).
   * @param {string} text
   * @param {Element} scope Nơi gắn ô nhập tạm (để chạy được trong Shadow DOM).
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
   * Gắn một nhãn chữ + biểu tượng vào nút.
   * @param {HTMLElement} button
   * @param {string} iconName
   * @param {string} label
   * @returns {HTMLElement} Phần tử chữ.
   */
  function iconButton(button, iconName, label) {
    const text = el("span", "", label);
    button.append(icon(iconName), text);
    return text;
  }

  /**
   * @typedef {object} ShieldView
   * @property {string} level
   * @property {string} levelLabel
   * @property {string} headline
   * @property {string} reasonShort
   * @property {{userinfo: string, prefix: string, decoyPrefix: boolean, registered: string, rest: string, hit: string,
   *   punycode: string, isIp: boolean, brand: string, official: string}} domain
   * @property {string} officialLine
   * @property {{icon: string, text: string}[]} details
   * @property {boolean} checking
   * @property {Record<string, string>} actions
   * @property {Record<string, string>} labels
   */

  /**
   * Dựng màn hình vào ``container``.
   * @param {Element} container Nơi gắn (ví dụ thân trang, hoặc <dialog> trong Shadow DOM).
   * @param {ShieldView} view
   * @param {object} [options]
   * @param {string} [options.idPrefix] Tiền tố id (để ``aria-labelledby`` trỏ tới câu kết luận).
   * @param {"dark" | "light" | ""} [options.theme] Ép chế độ sáng/tối (mặc định theo hệ thống).
   * @returns {{root: HTMLElement, back: HTMLButtonElement, proceed: HTMLButtonElement, headlineId: string,
   *   update: (next: ShieldView) => void, setLock: (secondsLeft: number, fraction: number) => void,
   *   note: (text: string) => void}}
   */
  function mount(container, view, options = {}) {
    const prefix = options.idPrefix ?? "chotto";
    const root = el("div", "sh");
    if (options.theme) root.dataset.theme = options.theme;

    const tile = el("span", "sh-tile");
    tile.setAttribute("aria-hidden", "true");
    const chip = el("span", "sh-chip");
    const head = el("div", "sh-head");
    // Điểm rủi ro to (chỉ có khi view có "score": Desktop). Thanh đầy theo điểm, màu theo mức.
    const scoreNum = el("span", "sh-score-num");
    const scoreOf = el("span", "sh-score-of", "/100");
    const scoreBar = el("i", "sh-score-bar");
    const score = el("div", "sh-score");
    score.setAttribute("role", "img");
    score.append(scoreNum, scoreOf, scoreBar);
    head.append(tile, chip, score);
    const headline = el("h1", "sh-headline");
    headline.id = `${prefix}-title`;
    const sub = el("p", "sh-sub");

    const domain = el("section", "sh-domain");
    const caption = el("div", "sh-cap");
    const url = el("div", "sh-url");
    const puny = el("div", "sh-puny");
    const status = el("div", "sh-status");
    status.setAttribute("aria-live", "polite");
    domain.append(caption, url, puny, status);
    domain.setAttribute("aria-labelledby", `${prefix}-cap`);
    caption.id = `${prefix}-cap`;

    const whyBtn = /** @type {HTMLButtonElement} */ (el("button", "sh-whybtn"));
    whyBtn.type = "button";
    whyBtn.setAttribute("aria-expanded", "false");
    const whyLabel = el("span");
    whyBtn.append(whyLabel, icon("chevron"));
    const whyBody = el("div", "sh-whybody");
    whyBody.id = `${prefix}-why`;
    whyBtn.setAttribute("aria-controls", whyBody.id);
    const whyList = el("ul");
    whyBody.append(whyList);
    whyBtn.addEventListener("click", () => {
      const open = whyBtn.getAttribute("aria-expanded") !== "true";
      whyBtn.setAttribute("aria-expanded", String(open));
      if (open) whyBody.dataset.open = "";
      else delete whyBody.dataset.open;
    });

    const back = /** @type {HTMLButtonElement} */ (el("button", "sh-back"));
    back.type = "button";
    back.autofocus = true;
    const backText = iconButton(back, "back", "");
    const copy = /** @type {HTMLButtonElement} */ (el("button", "sh-ghost"));
    copy.type = "button";
    const copyLabel = iconButton(copy, "copy", "");
    const report = /** @type {HTMLButtonElement} */ (el("button", "sh-ghost sh-report"));
    report.type = "button";
    const reportLabel = iconButton(report, "chat", "");
    const more = el("div", "sh-more");
    more.append(copy, report);
    const proceed = /** @type {HTMLButtonElement} */ (el("button", "sh-proceed"));
    proceed.type = "button";
    proceed.setAttribute("aria-disabled", "true");
    const ring = el("span", "sh-ring");
    ring.setAttribute("aria-hidden", "true");
    const ringSvg = document.createElementNS(SVG_NS, "svg");
    ringSvg.setAttribute("viewBox", "0 0 22 22");
    const bg = document.createElementNS(SVG_NS, "circle");
    const fg = document.createElementNS(SVG_NS, "circle");
    for (const [node, cls] of /** @type {[SVGElement, string][]} */ ([[bg, "bg"], [fg, "fg"]])) {
      node.setAttribute("class", cls);
      node.setAttribute("cx", "11");
      node.setAttribute("cy", "11");
      node.setAttribute("r", "9");
    }
    fg.setAttribute("stroke-dasharray", String(RING));
    fg.setAttribute("stroke-dashoffset", String(RING));
    ringSvg.append(bg, fg);
    const secs = el("span", "");
    ring.append(ringSvg, secs);
    const proceedLabel = el("span");
    proceed.append(ring, proceedLabel);
    const actions = el("div", "sh-actions");
    const noteLine = el("p", "sh-note");
    noteLine.setAttribute("role", "status");
    const hint = el("p", "sh-hint");
    actions.append(back, more, proceed, noteLine, hint);

    root.append(head, headline, sub, domain, whyBtn, whyBody, actions);
    container.append(root);

    /** @type {ShieldView | null} */
    let shown = null;
    let waitTemplate = "";
    let lastLeft = Infinity;

    /**
     * Tên miền: tiền tố/user@ (nhạt, gạch đi nếu ngụy trang), tên miền đăng ký (đậm, tô sáng phần giống thương hiệu), phần còn lại (nhạt).
     * @param {ShieldView["domain"]} d
     */
    const renderUrl = (d) => {
      url.replaceChildren();
      if (d.userinfo) url.append(el("span", "u-user", clean(d.userinfo)));
      if (d.prefix) {
        const node = el("span", "u-prefix", clean(d.prefix));
        if (d.decoyPrefix) node.dataset.decoy = "";
        url.append(node);
      }
      const reg = el("b", "u-reg");
      const text = clean(d.registered);
      const hit = clean(d.hit);
      const from = hit ? text.indexOf(hit) : -1;
      const to = from >= 0 ? from + hit.length : -1;
      const odd = Boolean(d.punycode);      // tên miền Unicode: gạch sóng các ký tự ngoài ASCII (có thể là chữ giả dạng chữ Latin)
      /** @type {HTMLElement} */
      let into = reg;
      let chunk = "";
      const flush = () => {
        if (chunk) into.append(document.createTextNode(chunk));
        chunk = "";
      };
      Array.from(text).reduce((index, ch) => {
        if (index === from) {
          flush();
          const mark = el("mark");
          reg.append(mark);
          into = mark;
        }
        if (odd && (ch.codePointAt(0) ?? 0) > 127) {
          flush();
          into.append(el("i", "odd", ch));
        } else {
          chunk += ch;
        }
        if (index + ch.length === to) {
          flush();
          into = reg;
        }
        return index + ch.length;
      }, 0);
      flush();
      url.append(reg);
      if (d.rest) url.append(el("span", "u-rest", clean(d.rest)));
    };

    /** @param {ShieldView} next */
    const update = (next) => {
      const changed = shown !== null && (shown.headline !== next.headline || shown.level !== next.level);
      const level = ["WARN", "HIGH", "BLOCKED"].includes(next.level) ? next.level : "WARN";
      root.dataset.level = level;
      tile.replaceChildren(icon(level === "BLOCKED" ? "blocked" : level === "HIGH" ? "high" : "warn"));
      chip.textContent = clean(next.levelLabel);
      const points = Number(/** @type {any} */ (next).score);
      score.hidden = !Number.isFinite(points);
      if (!score.hidden) {
        scoreNum.textContent = String(Math.round(points));
        scoreBar.style.setProperty("--fill", `${Math.max(0, Math.min(100, points))}%`);
        score.setAttribute("aria-label", `${Math.round(points)}/100`);
      }
      if (next.checking) headline.dataset.reserve = "";     // Tầng 3 còn chạy: câu kết luận có thể đổi, giữ chỗ 2 dòng để bố cục không nhảy
      headline.textContent = clean(next.headline);
      sub.textContent = clean(next.reasonShort);
      caption.textContent = clean(next.labels.caption);
      renderUrl(next.domain);
      puny.textContent = next.domain.punycode ? clean(next.domain.punycode) : "";
      puny.hidden = !next.domain.punycode;
      status.replaceChildren();
      if (next.checking) {
        status.dataset.busy = "";
        status.append(el("i", "sh-skel"), el("span", "", clean(next.labels.checking)));
      } else {
        delete status.dataset.busy;
        if (next.officialLine) {
          const line = el("span", "sh-official");
          const official = clean(next.domain.official);
          const text = clean(next.officialLine);
          const at = official ? text.lastIndexOf(official) : -1;
          if (at >= 0) line.append(document.createTextNode(text.slice(0, at)), el("b", "", official), document.createTextNode(text.slice(at + official.length)));
          else line.textContent = text;
          line.prepend(icon("check"));
          status.append(line);
        }
      }
      whyLabel.textContent = clean(next.labels.why);
      whyList.replaceChildren();
      for (const row of next.details) {
        const item = el("li");
        item.append(icon(row.icon), el("span", "", clean(row.text)));
        whyList.append(item);
      }
      whyBtn.hidden = whyBody.hidden = next.details.length === 0;
      backText.textContent = clean(next.actions.back);
      copyLabel.textContent = clean(next.actions.copy);
      reportLabel.textContent = clean(next.actions.report);
      proceedLabel.textContent = clean(next.actions.proceed);
      hint.textContent = clean(next.actions.hint);
      waitTemplate = clean(next.labels.proceedWait);
      if (changed) {
        for (const node of [headline, tile, chip]) {
          node.classList.remove("sh-flash");
          void node.offsetWidth;
          node.classList.add("sh-flash");
        }
      }
      shown = next;
    };

    /**
     * @param {HTMLElement} button
     * @param {HTMLElement} label
     * @param {string} doneKey
     * @param {() => string} text
     */
    const wireShare = (button, label, doneKey, text) => {
      button.addEventListener("click", async () => {
        if (!shown) return;
        const ok = await copyText(text(), root);
        noteLine.textContent = ok ? clean(shown.actions[doneKey]) : "";
        if (ok) {
          const old = label.textContent;
          label.textContent = clean(shown.actions[doneKey]);
          setTimeout(() => { label.textContent = old; }, 2200);
        }
      });
    };
    wireShare(copy, copyLabel, "copied", () => String(shown?.actions.copyText ?? ""));
    wireShare(report, reportLabel, "reported", () => String(shown?.actions.reportText ?? ""));

    update(view);

    return {
      root,
      back,
      proceed,
      headlineId: headline.id,
      update,
      /**
       * Cập nhật vòng đếm ngược của nút "vẫn mở".
       * @param {number} secondsLeft Số giây còn lại (làm tròn lên); 0 = đã mở khóa.
       * @param {number} fraction Phần thời gian còn lại, 0..1 (vòng tròn).
       */
      setLock(secondsLeft, fraction) {
        fg.setAttribute("stroke-dashoffset", String(RING * Math.max(0, Math.min(1, fraction))));
        if (secondsLeft === lastLeft) return;
        lastLeft = secondsLeft;
        if (secondsLeft > 0) {
          proceed.setAttribute("aria-disabled", "true");
          secs.textContent = String(secondsLeft);
          proceed.setAttribute("aria-label", waitTemplate.replace("{n}", String(secondsLeft)));
        } else {
          proceed.setAttribute("aria-disabled", "false");
          proceed.removeAttribute("aria-label");
        }
      },
      /** @param {string} text */
      note(text) {
        noteLine.textContent = text;
      },
    };
  }

  /** @type {any} */ (globalThis).ChottoShield = Object.freeze({ mount, clean });
})();
