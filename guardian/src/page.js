// Giao diện trang người giám hộ. Chạy sau bảng module (__modules) và dữ liệu (__data) do tools/build_guardian_page.py dựng.
// KHÔNG gọi mạng (không dùng API mạng nào; CSP cũng chặn connect-src). Mọi chữ gán bằng textContent (không dựng HTML từ chuỗi).
const { computeCode, fromBase64Url, toBase64Url } = __modules.codec;
const { parseShareFragment } = __modules.share;
const { loadEngineData } = __modules.data;
const { Fingerprints, keysFromLines, protectedDomains } = __modules.tier1;
const { Engine } = __modules.engine;
const { buildView } = __modules.view;
const { normalizeDomain, normalizeNonce } = __modules.codec;

const STORAGE_KEY = "chotto-guardian-secret-v1";
const SETUP_PREFIX = "CHOTTO-GUARDIAN-SETUP-v1:";
const app = document.getElementById("app");

const TEXT = {
  title: "Có người nhờ bạn xem giúp một link",
  homeTitle: "Trang người giám hộ",
  homeLead: "Chưa có lời nhắn nào. Khi có người nhờ, hãy mở liên kết họ gửi qua Zalo.",
  address: "Bạn đang ở trang: ",
  siteCaption: "Trang web cần xem",
  onlySite: "CHOTTO chỉ chấm theo tên trang web, không thấy phần đường dẫn phía sau.",
  safe: "CHOTTO chưa thấy dấu hiệu lừa đảo ở tên trang web này.",
  safeHeadline: "Chưa thấy dấu hiệu lừa đảo",
  dangerBanner: "Đây có thể là lừa đảo. Chỉ cho mở nếu bạn chắc chắn.",
  warnBanner: "Trang này đáng ngờ. Hãy hỏi lại người nhờ bạn cho chắc.",
  deny: "Không cho mở",
  allow: "Cho mở",
  confirmAsk: "Bạn đã gọi lại cho người nhờ bằng số điện thoại quen thuộc để hỏi chưa?",
  confirmNo: "Chưa, quay lại",
  confirmYes: "Rồi, vẫn cho mở",
  denyReply: "Đừng mở link này nhé.",
  denyDone: "Đã chép câu trả lời. Dán vào Zalo rồi gửi cho họ.",
  codeCaption: "Mã mở khóa",
  codeNote: "Mã chỉ dùng được một lần, trong vài phút, và chỉ mở đúng trang này.",
  copyCode: "Chép mã",
  copyReply: "Chép câu trả lời",
  allowDone: "Đã chép câu trả lời có mã. Dán vào Zalo rồi gửi cho họ.",
  copied: "Đã chép.",
  copyFailed: "Chưa chép được. Bạn có thể bấm giữ vào chữ rồi chọn Sao chép.",
  replyCaption: "Câu trả lời soạn sẵn",
  setupTitle: "Cài đặt một lần",
  setupLead: "Dán chuỗi cài đặt do công cụ của bạn tạo ra (hoặc mở liên kết cài đặt bằng camera điện thoại). Bí mật chỉ nằm trên thiết bị này.",
  setupWarn: "Chỉ cài đặt khi chính bạn đã mở trang này từ liên kết của mình. Không bao giờ dán chuỗi cài đặt vào trang người lạ gửi.",
  setupLabel: "Chuỗi cài đặt",
  setupSave: "Lưu vào thiết bị này",
  setupBad: "Chuỗi cài đặt chưa đúng. Hãy chép lại cả chuỗi.",
  setupSaved: "Đã lưu vào thiết bị này.",
  setupStorage: "Trình duyệt không cho lưu dữ liệu trên trang này (chế độ riêng tư?). Hãy mở bằng cửa sổ thường.",
  setupLater: "Sau khi cài đặt xong, hãy mở lại liên kết người nhờ đã gửi.",
  installed: "Thiết bị này đã được cài đặt.",
  remove: "Xóa khỏi thiết bị này",
  removeAsk: "Xóa bí mật khỏi thiết bị này? Sau đó bạn phải cài đặt lại.",
  removeYes: "Xóa",
  removeNo: "Hủy",
  removed: "Đã xóa khỏi thiết bị này.",
  settings: "Cài đặt trên thiết bị này",
  settingsNote: "Bí mật được lưu trong trình duyệt của điện thoại này. Hãy đặt khóa màn hình, và bấm “Xóa khỏi thiết bị này” khi không dùng nữa.",
  manualTitle: "Người nhờ đọc mã qua điện thoại?",
  manualSite: "Tên trang web",
  manualCode: "Mã (12 ký tự)",
  manualGo: "Xem trang này",
  manualBad: "Tên trang web hoặc mã chưa đúng. Mã gồm 12 ký tự (không có chữ I, L, O và số 0, 1).",
  badLink: "Liên kết này không đọc được. Hãy nhờ người gửi tạo lời nhắn mới.",
  badVersion: "Liên kết này do bản khác tạo ra. Hãy nhờ người gửi tạo lời nhắn mới.",
  checking: "Đang xem trang web…",
  checkFailed: "Chưa xem được trang web này. Hãy hỏi lại người nhờ bạn.",
  home: "Về trang chính",
};

/** @type {{level: string, view: any} | null} */
let cachedEngine = null;

/**
 * Tạo phần tử (chữ gán bằng textContent).
 * @param {string} tag
 * @param {string} [cls]
 * @param {string} [text]
 */
function h(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

/**
 * @param {string} text
 * @param {string} [cls]
 * @param {() => void | Promise<void>} [onClick]
 */
function button(text, cls, onClick) {
  const b = h("button", `btn ${cls || ""}`.trim(), text);
  b.type = "button";
  if (onClick) b.addEventListener("click", onClick);
  return b;
}

// ------------------------------------------------------------ lưu bí mật trên thiết bị này

function loadSecret() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const bytes = fromBase64Url(raw);
    return bytes.length >= 16 ? bytes : null;
  } catch {
    return null;
  }
}

/** @param {Uint8Array} bytes */
function saveSecret(bytes) {
  try {
    localStorage.setItem(STORAGE_KEY, toBase64Url(bytes));
    return loadSecret() !== null;
  } catch {
    return false;
  }
}

function clearSecret() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* không có kho thì cũng không có gì để xóa */
  }
}

/**
 * Đọc chuỗi cài đặt: ``CHOTTO-GUARDIAN-SETUP-v1:<base64url>``, hoặc liên kết có ``#setup=<base64url>``, hoặc chính chuỗi base64url.
 * @param {string} text
 * @returns {Uint8Array | null}
 */
function parseSetup(text) {
  let value = String(text).trim();
  const at = value.indexOf("#setup=");
  if (at >= 0) value = new URLSearchParams(value.slice(at + 1)).get("setup") || "";
  else if (value.startsWith(SETUP_PREFIX)) value = value.slice(SETUP_PREFIX.length).trim();
  try {
    const bytes = fromBase64Url(value);
    return bytes.length >= 16 ? bytes : null;
  } catch {
    return null;
  }
}

// ------------------------------------------------------------ chấm điểm bằng engine của CHOTTO (chạy ngay trên máy)

async function getEngine() {
  if (cachedEngine) return cachedEngine;
  const data = await loadEngineData(async (name) => __data[name]);
  const { keys } = keysFromLines(data.seed, protectedDomains(data.rules));
  const fingerprints = await Fingerprints.fromKeys(keys);
  const engine = new Engine({
    rules: data.rules, advice: data.advice, settings: { tier3Enabled: false, aiAdvice: true },
    blacklist: async () => fingerprints, ageLookup: null,
  });
  cachedEngine = { engine, data };
  return cachedEngine;
}

/** @param {string} domain */
async function assess(domain) {
  const { engine, data } = await getEngine();
  const result = await engine.inspect(`https://${domain}/`);
  const view = result.level === "SAFE" ? null : buildView(result, { plain: data.plain, rules: data.rules });
  return { level: String(result.level), view };
}

// ------------------------------------------------------------ chép vào clipboard

/**
 * @param {string} text
 * @returns {Promise<boolean>}
 */
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    /* rơi xuống cách cũ */
  }
  const box = document.createElement("textarea");
  box.value = text;
  box.setAttribute("readonly", "");
  box.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0";
  document.body.append(box);
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

// ------------------------------------------------------------ các màn hình

function pageAddress() {
  const where = location.protocol === "file:" ? location.href.split("#")[0] : `${location.origin}${location.pathname}`;
  const line = h("p", "addr");
  line.append(document.createTextNode(TEXT.address), h("b", "", where));
  return line;
}

/** @param {string} message */
function show(message) {
  app.replaceChildren(h("p", "note", message));
}

/** Xóa phần #fragment khỏi thanh địa chỉ (không để bí mật nằm lại trong lịch sử). */
function clearHash() {
  try {
    history.replaceState(null, "", location.pathname + location.search);
  } catch {
    /* bỏ qua */
  }
}

/** @param {string | null} setupText Chuỗi cài đặt có sẵn từ liên kết (tùy chọn). @param {boolean} pendingLink */
function renderSetup(setupText, pendingLink) {
  const card = h("section", "card");
  card.append(h("h2", "", TEXT.setupTitle), h("p", "", TEXT.setupLead), h("p", "banner", TEXT.setupWarn));
  card.lastChild.dataset.level = "WARN";
  const label = h("label", "", TEXT.setupLabel);
  const input = /** @type {HTMLInputElement} */ (h("input"));
  input.type = "text";
  input.id = "setup-input";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.setAttribute("autocapitalize", "off");
  label.htmlFor = input.id;
  if (setupText) input.value = setupText;
  const status = h("p", "status");
  status.setAttribute("role", "status");
  const save = button(TEXT.setupSave, "primary", () => {
    const bytes = parseSetup(input.value);
    if (!bytes) {
      status.textContent = TEXT.setupBad;
      input.focus();
      return;
    }
    if (!saveSecret(bytes)) {
      status.textContent = TEXT.setupStorage;
      return;
    }
    input.value = "";
    clearHash();
    render(TEXT.setupSaved);
  });
  const actions = h("div", "actions");
  actions.append(save);
  card.append(label, input, actions, status);
  if (pendingLink) card.append(h("p", "note", TEXT.setupLater));
  app.replaceChildren(h("h1", "", TEXT.homeTitle), pageAddress(), card);
  if (setupText) save.focus();
}

/**
 * @param {string} message Thông báo ngắn ở đầu (ví dụ "Đã lưu vào thiết bị này.").
 */
function renderHome(message) {
  const children = [h("h1", "", TEXT.homeTitle), pageAddress()];
  if (message) {
    const done = h("p", "banner", message);
    done.dataset.level = "WARN";
    done.setAttribute("role", "status");
    children.push(done);
  }
  children.push(h("p", "", TEXT.homeLead));

  const manual = h("details");
  manual.append(h("summary", "", TEXT.manualTitle));
  const siteLabel = h("label", "", TEXT.manualSite);
  const site = /** @type {HTMLInputElement} */ (h("input"));
  site.type = "text";
  site.id = "manual-site";
  site.autocomplete = "off";
  site.spellcheck = false;
  site.setAttribute("autocapitalize", "off");
  siteLabel.htmlFor = site.id;
  const codeLabel = h("label", "", TEXT.manualCode);
  const code = /** @type {HTMLInputElement} */ (h("input"));
  code.type = "text";
  code.id = "manual-code";
  code.autocomplete = "off";
  code.spellcheck = false;
  code.setAttribute("autocapitalize", "characters");
  codeLabel.htmlFor = code.id;
  const status = h("p", "status");
  status.setAttribute("role", "status");
  const go = button(TEXT.manualGo, "primary", () => {
    const domain = normalizeDomain(site.value.replace(/\[\.\]/g, "."));
    const nonce = normalizeNonce(code.value);
    if (domain === null || nonce === null) {
      status.textContent = TEXT.manualBad;
      return;
    }
    renderReview(domain, nonce);
  });
  const actions = h("div", "actions");
  actions.append(go);
  manual.append(siteLabel, site, codeLabel, code, actions, status);
  children.push(manual, settingsBlock());
  app.replaceChildren(...children);
}

/** Khối "Cài đặt trên thiết bị này" với nút xóa hai bước. */
function settingsBlock() {
  const wrap = h("details");
  wrap.append(h("summary", "", TEXT.settings), h("p", "", TEXT.installed), h("p", "note", TEXT.settingsNote));
  const holder = h("div", "actions");
  const status = h("p", "status");
  status.setAttribute("role", "status");
  const ask = button(TEXT.remove, "secondary small", () => {
    const confirm = h("div", "confirm");
    confirm.append(h("p", "", TEXT.removeAsk));
    const row = h("div", "row two");
    row.append(
      button(TEXT.removeNo, "secondary small", () => holder.replaceChildren(ask)),
      button(TEXT.removeYes, "primary small", () => {
        clearSecret();
        render(TEXT.removed);
      }),
    );
    confirm.append(row);
    holder.replaceChildren(confirm);
  });
  holder.append(ask);
  wrap.append(holder, status);
  return wrap;
}

/**
 * Màn hình duyệt một link.
 * @param {string} domain Tên miền ASCII chuẩn.
 * @param {string} nonce Mã 12 ký tự chuẩn.
 */
async function renderReview(domain, nonce) {
  app.replaceChildren(h("h1", "", TEXT.title), pageAddress());
  const site = h("section", "card");
  const siteText = h("div", "site", domain);
  siteText.setAttribute("translate", "no");
  site.append(h("span", "cap", TEXT.siteCaption), siteText);
  app.append(site, h("p", "note", TEXT.checking));

  /** @type {{level: string, view: any}} */
  let verdict;
  try {
    verdict = await assess(domain);
  } catch (error) {
    console.error("CHOTTO: không chấm được", error);
    app.lastChild.textContent = TEXT.checkFailed;
    return;
  }
  app.lastChild.remove();

  const danger = verdict.level === "HIGH" || verdict.level === "BLOCKED";
  const box = h("section", "verdict");
  box.dataset.level = verdict.level;
  if (verdict.view) {
    box.append(h("div", "chip", verdict.view.levelLabel), h("p", "headline", verdict.view.headline));
    if (verdict.view.reasonShort) box.append(h("p", "reason", verdict.view.reasonShort));
  } else {
    box.append(h("div", "chip", TEXT.safeHeadline), h("p", "reason", TEXT.safe));
  }
  app.append(box);
  if (verdict.level !== "SAFE") {
    const banner = h("p", "banner", danger ? TEXT.dangerBanner : TEXT.warnBanner);
    banner.dataset.level = danger ? verdict.level : "WARN";
    banner.setAttribute("role", "alert");
    app.append(banner);
  }
  app.append(h("p", "note", TEXT.onlySite));

  const result = h("section", "result");
  result.hidden = true;
  result.tabIndex = -1;
  const status = h("p", "status");
  status.setAttribute("role", "status");
  const confirm = h("div", "confirm");
  confirm.hidden = true;

  const denyBtn = button(TEXT.deny, "primary", async () => {
    confirm.hidden = true;
    showReply(TEXT.denyReply, null, TEXT.denyDone);
  });
  const allowBtn = button(TEXT.allow, "secondary", () => {
    if (danger) {
      confirm.hidden = false;
      confirmNo.focus();
    } else {
      reveal();
    }
  });
  const confirmNo = button(TEXT.confirmNo, "primary small", () => {
    confirm.hidden = true;
    denyBtn.focus();
  });
  const confirmYes = button(TEXT.confirmYes, "secondary small", () => {
    confirm.hidden = true;
    reveal();
  });
  const row = h("div", "row two");
  row.append(confirmNo, confirmYes);
  confirm.append(h("p", "", TEXT.confirmAsk), row);

  /**
   * Hiện câu trả lời soạn sẵn (và mã nếu có) rồi tự chép câu trả lời.
   * @param {string} reply
   * @param {string | null} codeText "123 456" hoặc ``null`` khi từ chối.
   * @param {string} doneText
   */
  async function showReply(reply, codeText, doneText) {
    result.replaceChildren();
    result.hidden = false;
    if (codeText !== null) {
      const codeEl = h("div", "code", codeText);
      codeEl.setAttribute("translate", "no");
      codeEl.setAttribute("aria-label", `${TEXT.codeCaption}: ${codeText.split("").join(" ")}`);
      result.append(h("span", "cap", TEXT.codeCaption), codeEl, h("p", "note", TEXT.codeNote));
      const copyCodeBtn = button(TEXT.copyCode, "secondary small", async () => {
        status.textContent = (await copyText(codeText)) ? TEXT.copied : TEXT.copyFailed;
      });
      result.append(copyCodeBtn);
    }
    const replyEl = h("div", "reply", reply);
    const copyReplyBtn = button(TEXT.copyReply, "primary small", async () => {
      status.textContent = (await copyText(reply)) ? TEXT.copied : TEXT.copyFailed;
    });
    result.append(h("span", "cap", TEXT.replyCaption), replyEl, copyReplyBtn, status);
    status.textContent = (await copyText(reply)) ? doneText : TEXT.copyFailed;
    result.focus();
  }

  async function reveal() {
    const secret = loadSecret();
    if (secret === null) {
      render();
      return;
    }
    const raw = await computeCode(secret, domain, nonce);
    const spaced = `${raw.slice(0, 3)} ${raw.slice(3)}`;
    await showReply(`Mã của bạn là ${spaced}`, spaced, TEXT.allowDone);
  }

  const actions = h("div", "actions");
  actions.id = "decision";
  actions.append(denyBtn, allowBtn);
  app.append(actions, confirm, result, settingsBlock());
  denyBtn.focus();
}

/** @param {string} [message] Thông báo ngắn. */
function render(message) {
  const secret = loadSecret();
  const hash = location.hash;
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  const setupText = params.get("setup");
  if (setupText) {
    // Liên kết cài đặt (mã quét bằng camera): hiện để người dùng bấm "Lưu"; không tự lưu khi chưa được bấm.
    renderSetup(setupText, false);
    return;
  }
  const parsed = parseShareFragment(hash);
  if (!parsed.ok && parsed.reason !== "empty") {
    show(parsed.reason === "version" ? TEXT.badVersion : TEXT.badLink);
    return;
  }
  if (secret === null) {
    renderSetup(null, parsed.ok);
    return;
  }
  if (parsed.ok) {
    renderReview(parsed.domain, parsed.nonce);
    return;
  }
  renderHome(message || "");
}

window.addEventListener("hashchange", () => render());
render();

// Chạy được khi mất mạng: service worker (cùng thư mục) giữ một bản của trang. Chỉ khi mở qua http(s); trang không gọi mạng.
if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
  navigator.serviceWorker.register("sw.js").catch(() => undefined);
}
