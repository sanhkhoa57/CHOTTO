'use strict';

const { createHash, timingSafeEqual } = require('node:crypto');
const { isIP } = require('node:net');

const PAGE_SIZE = 60;
const HISTORY_SIZE = 1000;
const ID = /^\d{1,19}-\d{1,19}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

// The sender picks their own UUID, so only the per-address limits stop flooding.
const BURST_LIMIT = 5; // per address, every 10 seconds
const DAY_LIMIT = 200; // per address, 24 hours from its first message

// A link in an anti-scam room is most likely bait, even as plain text.
const LINK = new RegExp('(?:https?|hxxps?|ftp)://|www\\.|(?<![\\p{L}\\p{N}])(?:' +
  '(?:[a-z0-9-]+\\.)+(?:com|net|org|vn|info|biz|xyz|top|icu|cc|tk|ml|ga|cf|gq|io|co|me|ly|gl|gd|' +
  'app|dev|site|online|shop|store|live|club|vip|link|click|fun|pro|asia|ru|cn|us|uk|tv|ws|page|' +
  'id|sbs|cfd|buzz|win|bet|zip|mov|xn--[a-z0-9-]+)|(?:\\d{1,3}\\.){3}\\d{1,3})' +
  '(?![\\p{L}\\p{N}])', 'iu');
const RESERVED_NAME = /chotto|admin|quantri|moderator|^mod$/;

// Drops invisible and control characters (keeping the emoji joiner), flattens
// line breaks and caps stacked accents.
function clean(value) {
  return value.normalize('NFC')
    .replace(/\s+/g, ' ')
    .replace(/(?!‍)[\p{Cc}\p{Cf}]/gu, '')
    .replace(/(\p{M}{3})\p{M}+/gu, '$1')
    .trim();
}

const isBlank = (value) => !value.replace(/[\s\p{Default_Ignorable_Code_Point}\p{M}⠀]/gu, '');
const hasLink = (value) => LINK.test(value.normalize('NFKC').replace(/。/g, '.')
  .replace(/\p{Default_Ignorable_Code_Point}/gu, ''));
const isReservedName = (value) => RESERVED_NAME.test(value.normalize('NFKD').toLowerCase()
  .replace(/đ/g, 'd').replace(/[^a-z0-9]/g, ''));

const sha256 = (value) => createHash('sha256').update(value).digest('hex');
const authorOf = (client) => sha256(client).slice(0, 32);

// The sender's UUID stays private: readers only get its hash. Messages saved
// before this change still carry `client`.
const publicMessage = ({ id, client, author, name, text }) =>
  ({ id, author: author || authorOf(client), name, text });

// Check retries and posting limits inside the same operation as the append.
const SEND = `
  local previous = redis.call('GET', KEYS[2])
  if previous then return previous end
  if redis.call('EXISTS', KEYS[3]) == 1 then return false end
  if tonumber(redis.call('GET', KEYS[4]) or '0') >= ${BURST_LIMIT} then return false end
  if tonumber(redis.call('GET', KEYS[5]) or '0') >= ${DAY_LIMIT} then return 'day' end
  local count = redis.call('INCR', KEYS[4])
  if count == 1 then redis.call('EXPIRE', KEYS[4], 10) end
  local daily = redis.call('INCR', KEYS[5])
  if daily == 1 then redis.call('EXPIRE', KEYS[5], 86400) end
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
      const sender = message.author;
      return command(url, token, ['EVAL', SEND, 5, key,
        `${key}:sent:${sender}:${nonce}`, `${key}:sender:${sender}`,
        `${key}:rate:${source}`, `${key}:day:${source}`, HISTORY_SIZE, JSON.stringify(message)]);
    },
    remove(id) {
      return command(url, token, ['XDEL', key, id]);
    }
  };
}

async function communityChat(req, res, localStore) {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'GET' && req.method !== 'POST' && req.method !== 'DELETE') {
    res.setHeader('Allow', 'GET, POST, DELETE');
    return res.status(405).json({ error: 'method' });
  }

  const url = process.env.UPSTASH_REDIS_REST_URL || process.env.KV_REST_API_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN || process.env.KV_REST_API_TOKEN;
  if (!localStore && (!url || !token)) return res.status(503).json({ error: 'unconfigured' });
  const store = localStore || redisStore(url, token);

  try {
    if (req.method === 'DELETE') {
      // Moderation: off until a long COMMUNITY_ADMIN_KEY is configured.
      const key = process.env.COMMUNITY_ADMIN_KEY || '';
      const given = req.headers.authorization || '';
      if (key.length < 24 || !timingSafeEqual(Buffer.from(sha256(given)),
        Buffer.from(sha256(`Bearer ${key}`)))) {
        return res.status(401).json({ error: 'unauthorized' });
      }
      const { id } = req.query || {};
      if (typeof id !== 'string' || !ID.test(id)) return res.status(400).json({ error: 'invalid_id' });
      return res.status(200).json({ removed: Number(await store.remove(id)) });
    }

    if (req.method === 'GET') {
      const { after } = req.query || {};
      if (after !== undefined && (typeof after !== 'string' || !ID.test(after))) {
        return res.status(400).json({ error: 'invalid_cursor' });
      }
      const entries = await store.list(after, after ? PAGE_SIZE + 1 : PAGE_SIZE);
      const more = entries.length > PAGE_SIZE;
      const messages = entries.slice(0, PAGE_SIZE).map(publicMessage);
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
    // Validate shape and size first, then clean and moderate the content.
    if (typeof client !== 'string' || !UUID.test(client) || typeof nonce !== 'string' ||
        !UUID.test(nonce) || typeof name !== 'string' || name.length > 28 ||
        typeof text !== 'string' || text.length > 500) {
      return res.status(400).json({ error: 'invalid_message' });
    }
    const content = clean(text);
    const nickname = isBlank(clean(name)) ? '' : clean(name);
    if (isBlank(content)) return res.status(400).json({ error: 'invalid_message' });
    if (hasLink(content) || hasLink(nickname)) return res.status(400).json({ error: 'link' });
    if (isReservedName(nickname)) return res.status(400).json({ error: 'reserved_name' });
    const forwarded = process.env.VERCEL === '1' ? req.headers['x-vercel-forwarded-for'] : '';
    const remote = typeof forwarded === 'string' ? forwarded.split(',')[0].trim() : '';
    const rateKey = isIP(remote) ? remote : (req.socket?.remoteAddress || 'unknown');
    const source = sha256(rateKey);
    const author = authorOf(client.toLowerCase());
    const message = {
      author,
      name: nickname || `Khách ${author.slice(0, 4).toUpperCase()}`,
      text: content
    };
    const id = await store.append(message, nonce.toLowerCase(), source);
    if (id === 'day') return res.status(429).json({ error: 'daily_limit' });
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
