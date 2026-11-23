// Tô màu nhân vật taskbar để xem trước trong cửa sổ ứng dụng.
// Cùng thuật toán với chotto/mascot.py (recolor_pixels) và design/chotto_mascot_customizer.html:
// mask kênh R = số nhóm + 1, kênh G = 255 là điểm giữ nguyên. Tham số lấy từ chotto/mascot_assets/palette.json.
"use strict";
(() => {
  const hx = (c) => [1, 3, 5].map((i) => parseInt(c.substr(i, 2), 16));
  const lum = (c) => 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2];

  // src, mask, out: Uint8ClampedArray RGBA cùng kích thước. colors: 6 mã #rrggbb. P: palette.json.
  function recolor(src, mask, out, colors, P) {
    const T = colors.map(hx);
    const same = colors.map((c, k) => c.toLowerCase() === P.default[k].toLowerCase());
    const base = P.default.map(hx);
    const baseLum = base.map(lum);
    const blushK = 0.45 + 0.30 * Math.min(1, lum(T[2]) / baseLum[2]);
    for (let i = 0; i < src.length; i += 4) {
      const a = src[i + 3], k = mask[i] - 1;
      let r = src[i], g = src[i + 1], b = src[i + 2];
      if (a > 0 && k >= 0 && k < 6 && mask[i + 1] !== 255 && !same[k]) {
        const y = 0.299 * r + 0.587 * g + 0.114 * b;
        const pr = P.params[k];
        let w = Math.min(1, Math.max(0, (y - pr[0]) / (pr[1] - pr[0])));
        if (k === 1) {
          const mn = Math.min(r, g, b), mx = Math.max(r, g, b);
          if (mn > 212 && mx - mn < 28) w *= Math.min(1, Math.max(0, (232 - mn) / 20));
        }
        if (w > 0) {
          const yb = P.pivot[k], tk = T[k];
          let nr, ng, nb;
          if (y <= yb) {
            const sc = Math.pow(Math.max(0, y / yb), pr[2]);
            nr = tk[0] * sc; ng = tk[1] * sc; nb = tk[2] * sc;
          } else {
            const h = Math.min(1, (y - yb) / Math.max(1, 255 - yb)) * pr[3];
            nr = tk[0] + (255 - tk[0]) * h; ng = tk[1] + (255 - tk[1]) * h; nb = tk[2] + (255 - tk[2]) * h;
          }
          if (k === 2) {
            const bk = base[2], bs = y / baseLum[2];
            nr += (r - bk[0] * bs) * blushK; ng += (g - bk[1] * bs) * blushK; nb += (b - bk[2] * bs) * blushK;
          }
          nr = Math.min(255, Math.max(0, nr)); ng = Math.min(255, Math.max(0, ng)); nb = Math.min(255, Math.max(0, nb));
          const iw = 1 - w;
          r = Math.round(r * iw + nr * w); g = Math.round(g * iw + ng * w); b = Math.round(b * iw + nb * w);
        }
      }
      out[i] = r; out[i + 1] = g; out[i + 2] = b; out[i + 3] = a;
    }
  }

  window.CHOTTO_MASCOT = { recolor };
})();
