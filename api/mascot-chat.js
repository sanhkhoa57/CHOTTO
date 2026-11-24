// /api/mascot-chat: mascot Chotto trả lời ngắn về link đáng ngờ / app Chotto.
// Gemini Flash-Lite (miễn phí) là chính; DeepSeek chỉ chạy khi Gemini hết quota (429), lỗi máy chủ (5xx) hoặc quá hạn.
// Khóa đọc từ biến môi trường (Vercel: Project Settings > Environment Variables; cục bộ: .env). Không bao giờ ghi khóa vào mã.
// BỘ LỌC bên dưới phải khớp với bản trong index.html (khối "mascot chat"): sửa một nơi thì sửa cả hai.
'use strict';

const MIN_LEN = 4, MAX_LEN = 150, TIMEOUT_MS = 8000;

const DOMAIN_RE = /(https?:\/\/|www\.)\S+|[a-z0-9-]+\.(vn|com|top|xyz|net|org|info|click|site|online|tk|me|io|app)(?![a-z0-9])/i;
const KEYWORDS = ['chotto', 'scam', 'lừa đảo', 'giả mạo', 'phishing', 'link', 'url', 'tên miền', 'domain', 'mã độc', 'virus', 'trojan', 'hack',
  'mất nick', 'chiếm quyền', 'zalo', 'messenger', 'facebook', 'telegram', 'ngân hàng', 'vietcombank', 'mbbank', 'techcombank', 'momo', 'shopee',
  'shipper', 'sinh trắc', 'cài đặt', 'tải về', 'download', 'windows', 'macos', 'mac', 'arm', 'x86', 'extension', 'tiện ích', 'trình duyệt',
  'miễn phí', 'free', 'nhẹ', 'ram', 'bảo mật', 'an toàn', 'chặn'];
const BLACKLIST = ['viết code', 'giải bài', 'dịch sang', 'tóm tắt', 'viết văn', 'làm thơ', 'kể chuyện', 'sql', 'python', 'javascript', 'bài tập'];

// Từ ASCII ngắn ("mac", "ram", "arm", "free"...) phải khớp nguyên từ, kẻo "program" hay "machine" lọt qua; từ có dấu thì khớp chuỗi con.
function hasKeyword(text, w) {
  if (/^[a-z0-9 ]+$/.test(w)) return new RegExp('(^|[^a-z0-9])' + w + '([^a-z0-9]|$)').test(text);
  return text.includes(w);
}

function checkInput(raw) {
  if (typeof raw !== 'string') return false;
  const s = raw.trim();
  if (s.length < MIN_LEN || s.length > MAX_LEN) return false;
  const low = s.toLowerCase();
  if (BLACKLIST.some((b) => low.includes(b))) return false;
  return DOMAIN_RE.test(s) || KEYWORDS.some((k) => hasKeyword(low, k));
}

const SYSTEM_PROMPT = `Bạn là Chotto, linh vật chống lừa đảo Gen Z của ứng dụng Chotto (chotto.id.vn) - công cụ chặn link lừa đảo/phishing trên Zalo, Messenger và trình duyệt.
Nhiệm vụ duy nhất:
1. Phân tích nhanh mức độ an toàn của đường link/tên miền người dùng gửi (cảnh báo đuôi lạ, giả mạo ngân hàng/sàn TMĐT, link rút gọn).
2. Giải đáp ngắn gọn về app Chotto (miễn phí, siêu nhẹ, hỗ trợ Windows x86/ARM và trình duyệt, bảo vệ quyền riêng tư).
Quy tắc bắt buộc:
- Trả lời bằng tiếng Việt giọng Gen Z tỉnh táo, hài hước, trực diện.
- Tối đa 2 câu ngắn (dưới 50 từ).
- Nếu người dùng cố tình hỏi chủ đề khác ngoài bảo mật/link/Chotto, từ chối thẳng thừng trong 1 câu.`;

const FALLBACK_REPLY = 'Hôm nay tui soi nhiều link quá nên hơi lag não, bạn bấm tải Chotto về dùng thử cho trực quan nha!';
const ALERT_RE = /nguy hiểm|lừa đảo|scam|giả mạo|khoan|cẩn thận|(^|[^\p{L}])né([^\p{L}]|$)/iu;

// Trả về chuỗi trả lời, hoặc ném lỗi có `retry = true` khi nên chuyển sang dịch vụ dự phòng.
async function callChat(url, key, body) {
  let res;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + key },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (e) {
    throw Object.assign(new Error('network/timeout'), { retry: true });
  }
  if (!res.ok) throw Object.assign(new Error('http ' + res.status), { retry: res.status === 429 || res.status >= 500 });
  let data;
  try { data = await res.json(); } catch (e) { throw Object.assign(new Error('bad json'), { retry: true }); }
  const text = data && data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content;
  if (typeof text !== 'string' || !text.trim()) throw Object.assign(new Error('empty'), { retry: true });
  return text.trim();
}

async function askModels(message) {
  const messages = [{ role: 'system', content: SYSTEM_PROMPT }, { role: 'user', content: message }];
  const gKey = process.env.GEMINI_API_KEY;
  if (gKey) {
    try {
      return await callChat('https://generativelanguage.googleapis.com/v1beta/openai/chat/completions', gKey,
        { model: process.env.GEMINI_MODEL || 'gemini-3.5-flash-lite', messages, max_tokens: 80, temperature: 0.7 });
    } catch (e) {
      if (!e.retry) return null;                                   // lỗi không cứu được bằng dự phòng (vd. sai khóa): báo câu chữa cháy
    }
  }
  const dKey = process.env.DEEPSEEK_API_KEY;
  if (!dKey) return null;
  try {
    return await callChat('https://api.deepseek.com/chat/completions', dKey,
      { model: process.env.DEEPSEEK_MODEL || 'deepseek-flash', messages, max_tokens: 80, temperature: 0.7, thinking: { type: 'disabled' } });
  } catch (e) {
    return null;
  }
}

module.exports = async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'POST') { res.setHeader('Allow', 'POST'); return res.status(405).json({ error: 'method' }); }
  let body = req.body;
  if (typeof body === 'string') { try { body = JSON.parse(body); } catch (e) { body = null; } }
  const message = body && typeof body.message === 'string' ? body.message.trim() : '';
  if (!checkInput(message)) return res.status(400).json({ error: 'invalid' });

  const text = await askModels(message);
  if (!text) return res.status(200).json({ reply: FALLBACK_REPLY, bubbleType: 'normal' });
  const reply = text.replace(/[`*_#]/g, '').replace(/\s+/g, ' ').trim().slice(0, 400);   // bỏ ký hiệu markdown: giao diện hiển thị chữ thuần
  return res.status(200).json({ reply, bubbleType: ALERT_RE.test(reply) ? 'alert' : 'normal' });
};

module.exports.checkInput = checkInput;
