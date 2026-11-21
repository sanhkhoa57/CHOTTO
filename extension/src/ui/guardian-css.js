// CSS của giao diện Guardian (hai màn hình, thiết kế cho người lớn tuổi). Dùng các biến màu của .sh (shield.css) nên sáng/tối
// theo hệ thống. Quy ước: chữ thân >= 18px, tiêu đề >= 24px, vùng bấm >= 48px, không hoạt ảnh. Tương phản đo ở extension/tests/guardian-contrast.test.mjs.
globalThis.CHOTTO_GUARDIAN_CSS = `
/* ---- Màn hình 1: chặn. Chỉ hai nút chính; phần còn lại nằm trong "Thêm lựa chọn". ---- */
.sh[data-guardian] .sh-chip, .sh[data-guardian] .sh-cap, .sh[data-guardian] .sh-status, .sh[data-guardian] .sh-official b,
.sh[data-guardian] .sh-puny, .sh[data-guardian] .sh-whybtn, .sh[data-guardian] .sh-whybody li, .sh[data-guardian] .sh-note { font-size: 18px; }
.sh[data-guardian] .sh-headline { font-size: 32px; }
.sh[data-guardian] .sh-actions { gap: 14px; }
.sh[data-guardian] .sh-official { display: block; line-height: 1.5; }
.sh[data-guardian] .sh-official svg { display: inline-block; width: 20px; height: 20px; margin-right: 8px; vertical-align: -3px; }
.sh[data-guardian] .sh-whybtn { min-height: 48px; }
.sh[data-guardian] .sh-ghost { min-height: 52px; height: auto; padding: 8px 18px; font-size: 18px; }
.sh[data-guardian] .sh-note { min-height: 0; margin: 8px 0 0; color: var(--ink); }
.sh-ask { justify-self: stretch; margin-top: 0; height: 58px; padding: 0 22px; border-radius: 999px; font-size: 18px; font-weight: 600; color: var(--ink);
  display: inline-flex; align-items: center; justify-content: center; gap: 10px; background: var(--surface2); box-shadow: inset 0 0 0 1.5px var(--line-strong); }
.sh-ask:hover { box-shadow: inset 0 0 0 1.5px var(--ink); }
.sh-ask .gd-name, .gd-title .gd-name { font-weight: 800; }
.gd-more-toggle { display: block; min-height: 48px; margin: 8px auto 0; padding: 8px 14px; font-size: 18px; font-weight: 600; color: var(--ink);
  text-decoration: underline; text-underline-offset: 4px; border-radius: 10px; }
.gd-more-toggle[aria-expanded="true"] { text-decoration-style: dotted; }
.gd-more-body { margin-top: 4px; display: grid; gap: 4px; }
.gd-more-body[hidden], .gd-fallback-body[hidden] { display: none; }

/* ---- Màn hình 2: đã nhờ người giám hộ. Chỉ phần này hiện, phần của màn hình 1 ẩn đi. ---- */
.sh[data-step="2"] > :not(.gd) { display: none !important; }
.gd { margin: 0; }
.gd[hidden] { display: none; }
.gd-title { margin: 0; font: 400 28px/1.25 var(--serif); letter-spacing: -.01em; }
.gd-send { margin-top: 18px; padding: 16px 18px; border-radius: 16px; display: grid; gap: 10px; justify-items: start; background: var(--surface);
  box-shadow: inset 0 0 0 1.5px var(--line-strong); }
.gd-lead { margin: 0; min-height: 1.5em; font-size: 20px; font-weight: 700; color: var(--ink); }
.gd-how { margin: 0; font-size: 18px; line-height: 1.5; }
.gd-ghost { min-height: 52px; padding: 8px 22px; border-radius: 999px; font-size: 18px; font-weight: 600; box-shadow: inset 0 0 0 1.5px var(--line-strong); }
.gd-ghost:hover { background: var(--surface2); box-shadow: inset 0 0 0 1.5px var(--ink); }
.gd-form { margin-top: 22px; display: grid; gap: 12px; }
.gd-step { margin: 0; font-size: 18px; font-weight: 600; line-height: 1.5; }
.gd-code { width: 100%; min-width: 0; height: 72px; padding: 0 12px; text-align: center; border-radius: 16px; border: 0; background: var(--bg); color: var(--ink);
  font: 700 34px/1 var(--mono); letter-spacing: .12em; box-shadow: inset 0 0 0 2px var(--line-strong); caret-color: var(--ink); }
.gd-code:focus { outline: 3px solid var(--accent-hi); outline-offset: 2px; }
.gd-open { min-height: 58px; border-radius: 999px; font-size: 19px; font-weight: 700; background: var(--accent); color: var(--accent-ink); transition: background .2s; }
.gd-open:hover:not(:disabled) { background: var(--accent-hi); }
.gd-open:disabled { background: var(--surface2); color: var(--muted); cursor: not-allowed; box-shadow: inset 0 0 0 1px var(--line); }
.gd-status { margin: 0; min-height: 1.6em; font-size: 18px; font-weight: 600; line-height: 1.5; color: var(--ink); }
.gd-trust { margin: 0; font-size: 18px; line-height: 1.5; color: var(--muted); }
.gd-remind { margin: 14px 0 0; font-size: 18px; font-weight: 600; color: var(--warn-ink); }
.gd-remind[hidden] { display: none; }
.gd-lock { margin: 14px 0; font-size: 20px; font-weight: 600; color: var(--ink); }
.gd-fallback { margin-top: 14px; }
.gd-fallback-body { margin-top: 6px; padding: 16px 18px; border-radius: 16px; display: grid; gap: 14px; background: var(--surface); box-shadow: inset 0 0 0 1px var(--line-strong); }
.gd-fig { display: grid; gap: 4px; }
.gd-cap { display: block; font-size: 18px; font-weight: 600; color: var(--muted); }
.gd-domain { font: 700 22px/1.3 var(--mono); overflow-wrap: anywhere; word-break: break-word; user-select: text; }
.gd-nonce { font: 700 34px/1.2 var(--mono); letter-spacing: .06em; color: var(--ink); user-select: text; overflow-wrap: anywhere; }
.gd-qr { width: 200px; height: 200px; border-radius: 10px; overflow: hidden; box-shadow: 0 0 0 1px var(--line-strong); }
.gd-qr svg { display: block; width: 100%; height: 100%; }
.gd-qr svg rect, .gd-qr svg path { stroke: none; }
.gd-close { width: 100%; min-height: 54px; margin-top: 18px; border-radius: 999px; font-size: 18px; font-weight: 600; box-shadow: inset 0 0 0 1.5px var(--line-strong); }
.gd-close:hover { background: var(--surface2); box-shadow: inset 0 0 0 1.5px var(--ink); }
@media (max-width: 420px) { .gd-nonce, .gd-code { font-size: 28px; } .gd-title { font-size: 24px; } .sh[data-guardian] .sh-headline { font-size: 28px; } }
`;
