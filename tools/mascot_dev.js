// Chạy thử nội bộ mascot chat, không cần Vercel: node tools/mascot_dev.js  ->  http://127.0.0.1:5400
// Phục vụ file tĩnh của repo + chạy đúng hàm api/mascot-chat.js. Khóa đọc từ .env (không in ra).
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
try { process.loadEnvFile(path.join(ROOT, '.env')); } catch (e) { console.warn('Không đọc được .env (cần Node 20.12+ và file .env).'); }
const handler = require(path.join(ROOT, 'api', 'mascot-chat.js'));

const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.png': 'image/png', '.mp4': 'video/mp4',
  '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.json': 'application/json', '.zip': 'application/zip' };
const PUBLIC = /^\/(index\.html|favicon\.png|icon\.png|chotto\/web\/fonts\/[\w.-]+|chotto\/mascot\/assets\/pose_\d\.png)$/;   // chỉ phục vụ file trang cần, như vercel.json

http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x');
  if (url.pathname === '/api/mascot-chat') {
    let raw = '';
    req.on('data', (c) => { raw += c; if (raw.length > 4096) req.destroy(); });
    req.on('end', () => {
      try { req.body = JSON.parse(raw); } catch (e) { req.body = null; }
      res.status = (n) => { res.statusCode = n; return res; };
      res.json = (o) => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(o)); };
      handler(req, res);
    });
    return;
  }
  const p = url.pathname === '/' ? '/index.html' : decodeURIComponent(url.pathname);
  if (!PUBLIC.test(p)) { res.statusCode = 404; return res.end('404'); }
  fs.readFile(path.join(ROOT, p), (err, buf) => {
    if (err) { res.statusCode = 404; return res.end('404'); }
    res.setHeader('Content-Type', TYPES[path.extname(p)] || 'application/octet-stream');
    res.end(buf);
  });
}).listen(5400, '127.0.0.1', () => {
  console.log('Mở http://127.0.0.1:5400  (Gemini: ' + (process.env.GEMINI_API_KEY ? 'có khóa' : 'THIẾU khóa') +
    ', DeepSeek: ' + (process.env.DEEPSEEK_API_KEY ? 'có khóa' : 'THIẾU khóa') + ')');
});
