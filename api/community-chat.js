'use strict';

const { createHash } = require('node:crypto');
const { isIP } = require('node:net');

const PAGE_SIZE = 60;
const HISTORY_SIZE = 1000;
const ID = /^\d{1,19}-\d{1,19}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

// Check retries and posting limits inside the same operation as the append.
const SEND = `
  local previous = redis.call('GET', KEYS[2])
  if previous then return previous end
  if redis.call('EXISTS', KEYS[3]) == 1 then return false end
  if tonumber(redis.call('GET', KEYS[4]) or '0') >= 24 then return false end
  local count = redis.call('INCR', KEYS[4])
  if count == 1 then redis.call('EXPIRE', KEYS[4], 10) end
  local id = redis.call('XADD', KEYS[1], 'MAXLEN', ARGV[1], '*',
    'message', ARGV[2])
  redis.call('SET', KEYS[2], id, 'EX', 3600)
  redis.call('SET', KEYS[3], '1', 'EX', 1)
  return id
`;

async function command(url, token, parts) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(parts),
    signal: AbortSignal.timeout(5000)
  });
  if (!response.ok) throw new Error('Redis request failed');
  const { result, error } = await response.json();
  if (error || result === undefined) throw new Error('Redis command failed');
  return result;
}

function redisStore(url, token) {
  const key = `chotto:community:${process.env.VERCEL_ENV || 'development'}`;
  return {
    async list(after, size) {
      const entries = await command(url, token, after
        ? ['XRANGE', key, `(${after}`, '+', 'COUNT', size]
        : ['XREVRANGE', key, '+', '-', 'COUNT', size]);
      if (!after) entries.reverse();
      return entries.map(([id, [, payload]]) => ({ ...JSON.parse(payload), id }));
    },
    append(message, nonce, source) {
      const sender = message.client;
      return command(url, token, ['EVAL', SEND, 4, key,
        `${key}:sent:${sender}:${nonce}`, `${key}:sender:${sender}`,
        `${key}:rate:${source}`, HISTORY_SIZE, JSON.stringify(message)]);
    }
  };
}

async function communityChat(req, res, localStore) {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'GET' && req.method !== 'POST') {
    res.setHeader('Allow', 'GET, POST');
    return res.status(405).json({ error: 'method' });
  }

  const url = process.env.UPSTASH_REDIS_REST_URL || process.env.KV_REST_API_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN || process.env.KV_REST_API_TOKEN;
  if (!localStore && (!url || !token)) return res.status(503).json({ error: 'unconfigured' });
  const store = localStore || redisStore(url, token);

  try {
    if (req.method === 'GET') {
      const { after } = req.query || {};
      if (after !== undefined && (typeof after !== 'string' || !ID.test(after))) {
        return res.status(400).json({ error: 'invalid_cursor' });
      }
      const entries = await store.list(after, after ? PAGE_SIZE + 1 : PAGE_SIZE);
      const more = entries.length > PAGE_SIZE;
      const messages = entries.slice(0, PAGE_SIZE);
      res.setHeader('Vercel-CDN-Cache-Control', 'public, s-maxage=2');
      return res.status(200).json({ messages, more });
    }

    if (req.headers['content-type']?.split(';')[0].trim().toLowerCase() !== 'application/json') {
      return res.status(415).json({ error: 'content_type' });
    }
    let body = req.body;
    if (typeof body === 'string') {
      try { body = JSON.parse(body); } catch { body = null; }
    }
    const { client, nonce, name, text } = body || {};
    if (typeof client !== 'string' || !UUID.test(client) || typeof nonce !== 'string' ||
        !UUID.test(nonce) || typeof name !== 'string' || name.length > 28 ||
        typeof text !== 'string' || text.length > 500 || !text.trim()) {
      return res.status(400).json({ error: 'invalid_message' });
    }
    const forwarded = process.env.VERCEL === '1' ? req.headers['x-vercel-forwarded-for'] : '';
    const remote = typeof forwarded === 'string' ? forwarded.split(',')[0].trim() : '';
    const rateKey = isIP(remote) ? remote : (req.socket?.remoteAddress || 'unknown');
    const source = createHash('sha256').update(rateKey).digest('hex');
    const message = {
      client: client.toLowerCase(),
      name: name.trim() || `Khách ${client.slice(0, 4).toUpperCase()}`,
      text: text.trim()
    };
    const id = await store.append(message, nonce.toLowerCase(), source);
    if (!id) {
      res.setHeader('Retry-After', '2');
      return res.status(429).json({ error: 'rate_limit' });
    }
    return res.status(200).json({ id });
  } catch {
    return res.status(503).json({ error: 'unavailable' });
  }
}

module.exports = (req, res) => communityChat(req, res);
module.exports.withStore = (store) => (req, res) => communityChat(req, res, store);
