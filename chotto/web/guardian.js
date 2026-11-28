// Hộp thoại Guardian Mode dùng chung (app.html và friction.html). Mọi xác thực do Python làm (chotto/guardian.py);
// trang này không lưu và không tự kiểm PIN hay mã khôi phục.
//   askPin(api, {title, attempt})  -> câu trả lời của attempt(pin) khi PIN được nhận, hoặc null nếu hủy
//   createPin(api)                 -> {pin, contact} sau khi đặt PIN và xác nhận đã lưu mã khôi phục, hoặc null
//   changePin(api)                 -> true nếu đã đổi (hiện mã khôi phục mới, bắt buộc xác nhận đã lưu)
//   resetPin(api)                  -> true nếu đã đặt lại bằng mã khôi phục
//   close()                        -> đóng hộp thoại đang mở (coi như hủy); không đóng màn hình mã khôi phục bắt buộc
"use strict";
(() => {
  const I18N = window.CHOTTO_I18N;
  const t = (key, vars) => I18N.t(key, vars);
  let current = null;                     // hộp thoại đang mở: {finish}

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => { if (k === "text") node.textContent = v; else node.setAttribute(k, v); });
    node.append(...children);
    return node;
  }

  // Khung hộp thoại: build(card, finish, fail) dựng nội dung. Esc = hủy (nếu cho phép); phím không lọt xuống trang
  // (ở màn hình cảnh báo, Esc của trang nghĩa là đóng cả cửa sổ).
  function dialog(title, build, cancellable = true) {
    close();
    return new Promise((resolve) => {
      const card = el("form", { class: "gd-card", novalidate: "" }, el("h2", { id: "gdTitle", text: title }));
      const box = el("div", { class: "gd", role: "dialog", "aria-modal": "true", "aria-labelledby": "gdTitle" }, card);
      const before = document.activeElement;
      let timer = 0;
      const finish = (value) => {
        clearInterval(timer);
        document.removeEventListener("keydown", onKey, true);
        box.remove();
        current = null;
        if (before && before.focus) before.focus();
        resolve(value);
      };
      const onKey = (e) => {
        if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); if (cancellable) finish(null); return; }
        if (e.key !== "Tab") return;
        const stops = [...box.querySelectorAll("button:not(:disabled), input:not(:disabled)")];
        const first = stops[0], last = stops[stops.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      };
      const error = el("p", { class: "gd-error", role: "alert" });
      // Báo lỗi xác thực; bị tạm khóa thì đếm ngược và khóa nút gửi.
      const fail = (auth, fallback) => {
        clearInterval(timer);
        const submit = card.querySelector("[type=submit]");
        if (auth && auth.error === "locked") {
          const until = Date.now() + auth.locked_for * 1000;
          const tick = () => {
            const left = Math.max(0, Math.ceil((until - Date.now()) / 1000));
            if (submit) submit.disabled = left > 0;
            error.textContent = left ? t("g.err.locked", { t: `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}` }) : "";
            if (!left) clearInterval(timer);
          };
          timer = setInterval(tick, 500);
          tick();
        } else if (auth && auth.error === "wrong") error.textContent = t("g.err.wrong", { n: auth.attempts_left });
        else if (auth && auth.error === "invalid_pin") error.textContent = t("g.err.format");
        else if (auth && auth.error === "unavailable") error.textContent = t("g.err.unavailable");
        else error.textContent = fallback || t("g.err.generic");
      };
      current = { finish, cancellable };
      document.addEventListener("keydown", onKey, true);
      document.body.append(box);
      build(card, finish, fail, error);
      const target = card.querySelector("input, [type=submit]");
      if (target) target.focus();
    });
  }

  function close() { if (current && current.cancellable) current.finish(null); }

  function field(label, attrs) {
    const input = el("input", { autocomplete: "off", spellcheck: "false", ...attrs });
    return { row: el("label", { class: "gd-field" }, el("span", { text: label }), input), input };
  }
  function pinField(label) {
    const f = field(label, { type: "password", inputmode: "numeric", maxlength: "6", class: "gd-pin" });
    f.input.addEventListener("input", () => { f.input.value = f.input.value.replace(/\D/g, ""); });
    return f;
  }
  function buttons(submitLabel, onCancel) {
    const ok = el("button", { type: "submit", class: "gd-primary", text: submitLabel });
    const row = el("div", { class: "gd-btns" });
    if (onCancel) {
      const cancel = el("button", { type: "button", text: t("g.cancel") });
      cancel.addEventListener("click", onCancel);
      row.append(cancel);
    }
    row.append(ok);
    return { row, ok };
  }
  // Gửi biểu mẫu: chặn bấm đúp, lỗi gọi Python thì báo ngay trong hộp thoại.
  function onSubmit(card, ok, fail, handler) {
    let busy = false;
    card.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (busy || ok.disabled) return;
      busy = true;
      try { await handler(); } catch (err) { fail(null); } finally { busy = false; }
    });
  }
  function checkNew(a, b, fail) {
    if (!/^\d{4,6}$/.test(a.input.value)) { fail({ error: "invalid_pin" }); a.input.focus(); return false; }
    if (a.input.value !== b.input.value) { fail(null, t("g.err.mismatch")); b.input.value = ""; b.input.focus(); return false; }
    return true;
  }

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch (err) { /* thử cách cũ */ }
    const area = el("textarea");
    area.value = text;
    document.body.append(area);
    area.select();
    const done = document.execCommand("copy");
    area.remove();
    return done;
  }

  // Hiện mã khôi phục một lần; chỉ đi tiếp được sau khi tick "đã lưu".
  function showKey(key, cancellable) {
    return dialog(t("g.key.title"), (card, finish) => {
      const copy = el("button", { type: "button", class: "gd-link", text: t("g.key.copy") });
      copy.addEventListener("click", async () => { if (await copyText(key)) copy.textContent = t("g.key.copied"); });
      const box = el("input", { type: "checkbox" });
      const { row, ok } = buttons(t("g.key.done"), cancellable ? () => finish(null) : null);
      ok.disabled = true;
      box.addEventListener("change", () => { ok.disabled = !box.checked; });
      card.append(el("p", { text: t("g.key.body") }), el("div", { class: "gd-key", text: key }), copy,
        el("label", { class: "gd-check" }, box, el("span", { text: t("g.key.check") })), row);
      card.addEventListener("submit", (e) => { e.preventDefault(); if (box.checked) finish(true); });
    }, cancellable);
  }

  // Quên PIN: mã khôi phục + PIN mới, sau đó hiện mã khôi phục mới (bắt buộc xác nhận).
  async function resetPin(api) {
    const key = await dialog(t("g.forgot.title"), (card, finish, fail, error) => {
      const code = field(t("g.forgot.key"), { type: "text", maxlength: "40", placeholder: "CHOTTO-XXXX-XXXX-XXXX" });
      const a = pinField(t("g.pin.new")), b = pinField(t("g.pin.again"));
      const { row, ok } = buttons(t("g.forgot.submit"), () => finish(null));
      card.append(el("p", { text: t("g.forgot.body") }), code.row, a.row, b.row, error, row);
      onSubmit(card, ok, fail, async () => {
        if (!code.input.value.trim()) { code.input.focus(); return; }
        if (!checkNew(a, b, fail)) return;
        const reply = await api.guardian_recover(code.input.value, a.input.value);
        if (reply.ok) finish(reply.recovery_key); else fail(reply);
      });
    });
    if (!key) return false;
    await showKey(key, false);
    return true;
  }

  async function askPin(api, { title, attempt }) {
    let notice = "";
    for (;;) {
      const result = await dialog(title, (card, finish, fail, error) => {
        const pin = pinField(t("g.pin.current"));
        const { row, ok } = buttons(t("g.confirm"), () => finish(null));
        const lost = el("button", { type: "button", class: "gd-link", text: t("g.forgot.link") });
        lost.addEventListener("click", () => finish({ forgot: true }));
        if (notice) card.append(el("p", { text: notice }));
        card.append(pin.row, error, row, lost);
        onSubmit(card, ok, fail, async () => {
          if (!pin.input.value) { pin.input.focus(); return; }
          const reply = await attempt(pin.input.value);
          if (reply.ok || !reply.need_pin) { finish({ reply, pin: pin.input.value }); return; }
          pin.input.value = "";
          pin.input.focus();
          fail(reply.auth);
        });
      });
      if (!result) return null;
      if (!result.forgot) return result;
      if (await resetPin(api)) notice = t("g.forgot.ok");
    }
  }

  async function createPin(api, contactNow) {
    const made = await dialog(t("g.create.title"), (card, finish, fail, error) => {
      const a = pinField(t("g.pin.new")), b = pinField(t("g.pin.again"));
      const who = field(t("g.contact.optional"), { type: "text", maxlength: "80", placeholder: t("g.contact.ph") });
      who.input.value = contactNow || "";
      const { row, ok } = buttons(t("g.create.submit"), () => finish(null));
      card.append(el("p", { text: t("g.create.body") }), a.row, b.row, who.row, error, row);
      onSubmit(card, ok, fail, async () => {
        if (!checkNew(a, b, fail)) return;
        const reply = await api.guardian_setup(a.input.value);
        if (reply.ok) finish({ pin: a.input.value, contact: who.input.value.trim(), key: reply.recovery_key });
        else fail(null, reply.error);
      });
    });
    if (!made || !(await showKey(made.key, true))) return null;
    const confirmed = await api.guardian_confirm(made.pin);
    return confirmed.ok ? { pin: made.pin, contact: made.contact } : null;
  }

  async function changePin(api) {
    const key = await dialog(t("g.change"), (card, finish, fail, error) => {
      const old = pinField(t("g.pin.current")), a = pinField(t("g.pin.new")), b = pinField(t("g.pin.again"));
      const { row, ok } = buttons(t("g.confirm"), () => finish(null));
      card.append(old.row, a.row, b.row, error, row);
      onSubmit(card, ok, fail, async () => {
        if (!checkNew(a, b, fail)) return;
        const reply = await api.guardian_change_pin(old.input.value, a.input.value);
        if (reply.ok) finish(reply.recovery_key);
        else { old.input.value = ""; old.input.focus(); fail(reply); }
      });
    });
    if (!key) return false;
    await showKey(key, false);   // mã cũ đã vô hiệu: bắt buộc lưu mã mới
    return true;
  }

  window.ChottoGuardian = { askPin, createPin, changePin, resetPin, close };
})();
