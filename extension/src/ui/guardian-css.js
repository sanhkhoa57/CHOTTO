// CSS của màn hình xin phép người giám hộ. Dùng các biến màu của .sh (shield.css) nên sáng/tối theo hệ thống và đạt tương phản AA.
globalThis.CHOTTO_GUARDIAN_CSS = `
.sh-ask { justify-self: stretch; margin-top: 0; height: 54px; padding: 0 22px; border-radius: 999px; font-size: 16.5px; font-weight: 700; color: var(--ink);
  display: inline-flex; align-items: center; justify-content: center; gap: 10px; background: var(--surface2); box-shadow: inset 0 0 0 1.5px var(--line-strong); }
.sh-ask:hover { box-shadow: inset 0 0 0 1.5px var(--ink); }
.sh-ask[aria-expanded="true"] { box-shadow: inset 0 0 0 2px var(--accent); }
.sh-ask svg { width: 20px; height: 20px; }
.gd { margin-top: 18px; padding: 18px 20px 20px; border-radius: 18px; background: var(--surface); box-shadow: inset 0 0 0 1.5px var(--accent); }
.gd[hidden] { display: none; }
.gd-title { margin: 0; font: 400 24px/1.25 var(--serif); letter-spacing: -.01em; }
.gd-intro { margin: 6px 0 0; font-size: 15px; color: var(--muted); }
.gd-warn { margin: 12px 0 0; padding: 12px 14px; border-radius: 12px; font-size: 15px; font-weight: 600; line-height: 1.45;
  color: var(--high-ink); background: var(--high-chip); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--high) 45%, transparent); }
.gd-step { margin: 16px 0 8px; font-size: 15px; font-weight: 600; }
.gd-share { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start; }
.gd-left { flex: 1 1 220px; min-width: 0; display: grid; gap: 12px; }
.gd-cap { display: block; font-size: 13px; font-weight: 600; letter-spacing: .02em; color: var(--muted); }
.gd-domain { margin-top: 4px; font: 700 22px/1.3 var(--mono); overflow-wrap: anywhere; word-break: break-word; user-select: text; }
.gd-nonce { margin-top: 4px; font: 700 38px/1.15 var(--mono); letter-spacing: .08em; color: var(--accent-hi); user-select: text; }
.gd-qr { flex: none; width: 150px; height: 150px; border-radius: 10px; overflow: hidden; box-shadow: 0 0 0 1px var(--line-strong); }
.gd-qr svg { display: block; width: 100%; height: 100%; }
.gd-qr svg rect, .gd-qr svg path { stroke: none; }
.gd-count { margin: 12px 0 0; font-size: 13.5px; color: var(--muted); }
.gd-form { margin-top: 4px; display: grid; gap: 10px; }
.gd-row { margin-top: 6px; display: flex; gap: 8px; }
.gd-digit { width: 100%; max-width: 54px; min-width: 0; height: 60px; text-align: center; border-radius: 12px; border: 0; background: var(--bg); color: var(--ink);
  font: 700 28px/1 var(--mono); box-shadow: inset 0 0 0 1.5px var(--line-strong); caret-color: var(--accent-hi); }
.gd-digit:focus { outline: 3px solid var(--accent-hi); outline-offset: 2px; box-shadow: inset 0 0 0 1.5px var(--accent-hi); }
.gd-open { height: 54px; border-radius: 999px; font-size: 17px; font-weight: 700; background: var(--accent); color: var(--accent-ink); transition: background .2s; }
.gd-open:hover:not(:disabled) { background: var(--accent-hi); }
.gd-open:disabled { background: var(--surface2); color: var(--muted); cursor: not-allowed; box-shadow: inset 0 0 0 1px var(--line); }
.gd-lock { margin: 12px 0; font-size: 16px; font-weight: 600; color: var(--high-ink); }
.gd-status { margin: 12px 0 0; min-height: 1.5em; font-size: 15px; font-weight: 600; color: var(--ink); }
@media (max-width: 420px) { .gd-nonce { font-size: 32px; } .gd-digit { height: 54px; font-size: 24px; } }
`;
