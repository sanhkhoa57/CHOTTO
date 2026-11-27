"""API phòng chat cộng đồng: chạy api/community-chat.js bằng Node với kho giả."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCRIPT = r"""
const chat = require(process.argv[1]);
const saved = [{ id: '1-0', client: '11111111-1111-4111-8111-111111111111', name: 'Cu', text: 'tin cu' }];
const removed = [];
const handle = chat.withStore({
  list: () => saved,
  append: (message) => {
    if (message.text === 'het luot') return 'day';
    saved.push({ ...message, id: `${saved.length + 1}-0` });
    return saved[saved.length - 1].id;
  },
  remove: (id) => { removed.push(id); return 1; }
});

async function call(method, { body, query = {}, headers = {} } = {}) {
  const out = {};
  const res = {
    setHeader() {},
    status(code) { out.status = code; return res; },
    json(data) { out.body = data; return res; }
  };
  await handle({ method, body, query, socket: {},
    headers: { 'content-type': 'application/json', ...headers } }, res);
  return out;
}

(async () => {
  const uuid = '22222222-2222-4222-8222-222222222222';
  const post = (text, name = '') => call('POST', { body: { client: uuid, nonce: uuid, name, text } });
  const posts = [];
  for (const [text, name] of JSON.parse(process.argv[2])) posts.push(await post(text, name));
  const list = await call('GET');
  const remove = (key, auth) => {
    process.env.COMMUNITY_ADMIN_KEY = key;
    return call('DELETE', { query: { id: '1-0' }, headers: { authorization: auth } });
  };
  const long = 'k'.repeat(32);
  const deletes = [await remove('', 'Bearer '), await remove('short', 'Bearer short'),
    await remove(long, 'Bearer wrong'), await remove(long, `Bearer ${long}`)];
  console.log(JSON.stringify({ posts, list, deletes, removed, uuid }));
})();
"""

CASES = [
    ("Chào cả nhà, hôm nay ổn không?", "", 200, None),
    ("Mình nhận tin lúc 10.30, mất 1.500.000 đồng", "Lan", 200, None),
    ("gia đình 👨‍👩‍👧 ổn.\n\n\n\nnhé", "", 200, None),
    ("vào https://abc.example/x", "", 400, "link"),
    ("nhận quà ở zalo-qua.xyz nhé", "", 400, "link"),
    ("vào shopee​.vn", "", 400, "link"),
    ("ｓｃａｍ。ｃｏｍ", "", 400, "link"),
    ("vào 192.168.1.10/login", "", 400, "link"),
    ("chào", "www.qua.vn", 400, "link"),
    ("chào", "Chötto Admin", 400, "reserved_name"),
    ("chào", "Quản Trị Viên", 400, "reserved_name"),
    ("​ㅤ⠀", "", 400, "invalid_message"),
    ("het luot", "", 429, "daily_limit"),
]


@unittest.skipUnless(shutil.which("node"), "cần Node")
class CommunityChatTest(unittest.TestCase):
    def test_api(self) -> None:
        run = subprocess.run(
            ["node", "-e", SCRIPT, str(ROOT / "api/community-chat.js"),
             json.dumps([case[:2] for case in CASES])],
            capture_output=True, text=True, encoding="utf-8", check=True)
        out = json.loads(run.stdout)

        for (text, name, status, error), got in zip(CASES, out["posts"]):
            with self.subTest(text=text, name=name):
                self.assertEqual((got["status"], got["body"].get("error")), (status, error))

        messages = out["list"]["body"]["messages"]
        # UUID của người gửi (kể cả tin cũ) không bao giờ được trả ra.
        for message in messages:
            self.assertEqual(set(message), {"id", "author", "name", "text"})
        self.assertNotIn(out["uuid"], json.dumps(messages))
        self.assertNotIn("11111111-1111", json.dumps(messages))
        self.assertEqual(messages[3]["text"], "gia đình 👨‍👩‍👧 ổn. nhé")

        self.assertEqual([item["status"] for item in out["deletes"]], [401, 401, 401, 200])
        self.assertEqual(out["removed"], ["1-0"])


if __name__ == "__main__":
    unittest.main()
