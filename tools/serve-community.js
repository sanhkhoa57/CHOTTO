'use strict';

const { createServer } = require('node:http');
const { createReadStream } = require('node:fs');
const { stat } = require('node:fs/promises');
const { pipeline } = require('node:stream/promises');
const { resolve, extname } = require('node:path');
const chat = require('../api/community-chat');
const config = require('../vercel.json');

const root = resolve(__dirname, '..');
const port = Number(process.argv[2] || 3000);
const publicFiles = config.builds.filter(({ use }) => use === '@vercel/static')
  .map(({ src }) => src.split('*'));
const types = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json',
  '.png': 'image/png', '.webp': 'image/webp', '.woff2': 'font/woff2',
  '.woff': 'font/woff', '.mp4': 'video/mp4', '.gz': 'application/gzip'
};

function memoryStore() {
  const history = [];
  let lastTime = 0, sequence = 0;
  return {
    list(after, size) {
      const cursor = after?.split('-').map(BigInt);
      const rows = cursor ? history.filter(({ time, order }) =>
        time > cursor[0] || (time === cursor[0] && order > cursor[1])).slice(0, size) : history.slice(-size);
      return rows.map(({ message }) => message);
    },
    append(message, nonce, source) {
      const now = Math.max(Date.now(), lastTime);
      const recent = history.find(({ message: item, nonce: saved, time }) =>
        item.client === message.client && saved === nonce && now-time < 3600000);
      if (recent) return recent.message.id;
      if (history.some(({ message: item, time }) => item.client === message.client && now-time < 1000)) return null;
      if (history.filter((row) => row.source === source && now-row.time < 10000).length >= 24) return null;
      sequence = now === lastTime ? sequence+1 : 0;
      lastTime = now;
      const id = `${now}-${sequence}`;
      history.push({ message:{ ...message,id }, time:now, order:sequence, nonce, source });
      if (history.length > 1000) history.shift();
      return id;
    }
  };
}

const handleChat = chat.withStore(memoryStore());

function json(res, status, body) {
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.statusCode = status;
  res.end(JSON.stringify(body));
}

async function serve(req, res) {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname === '/api/community-chat') {
    req.query = Object.fromEntries(url.searchParams);
    if (req.method === 'POST') {
      let size = 0;
      const chunks = [];
      for await (const chunk of req.iterator({ destroyOnReturn:false })) {
        size += chunk.length;
        if (size > 8192) {
          req.resume();
          return json(res, 413, { error:'message_too_large' });
        }
        chunks.push(chunk);
      }
      req.body = Buffer.concat(chunks).toString('utf8');
    }
    res.status = (code) => {
      res.statusCode = code;
      return res;
    };
    res.json = (body) => json(res, res.statusCode, body);
    return handleChat(req,res);
  }
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.setHeader('Allow', 'GET, HEAD');
    return json(res, 405, { error:'method' });
  }
  const path = url.pathname === '/' ? 'community.html' : url.pathname.slice(1);
  const isPublic = publicFiles.some(([prefix,suffix]) => suffix === undefined ? path === prefix :
    path.startsWith(prefix) && path.endsWith(suffix) &&
    /^[\w.-]+$/.test(path.slice(prefix.length,path.length-suffix.length)));
  if (!isPublic) return json(res, 404, { error:'not_found' });
  const filename = resolve(root,path);
  const info = await stat(filename).catch(() => null);
  if (!info?.isFile()) return json(res, 404, { error:'not_found' });
  res.setHeader('Content-Type', types[extname(path)] || 'application/octet-stream');
  res.setHeader('Content-Length', info.size);
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'HEAD') return res.end();
  await pipeline(createReadStream(filename),res);
}

const server = createServer((req,res) => {
  serve(req,res).catch(() => {
    if (!res.headersSent && !res.destroyed) json(res,500,{ error:'local_server_error' });
    else res.destroy();
  });
});
server.listen(port,'127.0.0.1',() => {
  console.log(`Community preview: http://localhost:${server.address().port}/community.html`);
  console.log('Local chat messages are stored in memory until this process stops.');
});
