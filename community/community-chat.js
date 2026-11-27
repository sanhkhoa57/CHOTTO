(() => {
  const room = document.getElementById("community-chat");
  const toggle = document.getElementById("chat-toggle");
  const close = document.getElementById("chat-close");
  const log = document.getElementById("chat-log");
  const form = document.getElementById("chat-form");
  const name = document.getElementById("chat-name");
  const input = document.getElementById("chat-text");
  const send = document.getElementById("chat-send");
  const status = document.getElementById("chat-status");
  const notice = document.getElementById("chat-notice");
  const empty = document.getElementById("chat-empty");
  const endpoint = "/api/community-chat";
  const clock = new Intl.DateTimeFormat("vi-VN", { hour:"2-digit", minute:"2-digit" });
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  let client = crypto.randomUUID();
  try {
    const saved = localStorage.getItem("chotto-chat-guest") || "";
    if (uuid.test(saved)) client = saved.toLowerCase();
    localStorage.setItem("chotto-chat-guest", client);
    name.value = (localStorage.getItem("chotto-chat-name") || "").slice(0,28);
  } catch {
    // A private browsing session can still chat without storage.
  }
  // Same hash as the server: others only ever see this, never the UUID itself.
  let me = "";
  const identified = crypto.subtle.digest("SHA-256", new TextEncoder().encode(client)).then((hash) => {
    me = Array.from(new Uint8Array(hash,0,16), (byte) => byte.toString(16).padStart(2,"0")).join("");
    name.placeholder = "Khách " + me.slice(0,4).toUpperCase();
  });
  const rejected = {
    link:"Phòng chat không cho gửi link hay tên miền.",
    reserved_name:"Tên này dành cho quản trị. Hãy chọn tên khác.",
    invalid_message:"Tin nhắn không có nội dung hợp lệ.",
    daily_limit:"Mạng của bạn đã hết lượt gửi hôm nay."
  };

  let after = "", timer, syncing = false, sending = false, connected = false;
  let onScreen = false, failures = 0, idle = 0, retry = null;

  function append(messages) {
    const atBottom = log.scrollHeight-log.scrollTop-log.clientHeight < 32;
    const previousHeight = log.scrollHeight;
    const rows = document.createDocumentFragment();
    for (const { id, author, name: nickname, text } of messages) {
      const row = document.createElement("article");
      row.className = author === me ? "chat-message mine" : "chat-message";
      const meta = document.createElement("div");
      meta.className = "chat-meta";
      const label = document.createElement("strong");
      label.textContent = author === me ? nickname + " (bạn)" : nickname;
      const time = document.createElement("time");
      const sentAt = new Date(Number(id.split("-")[0]));
      time.dateTime = sentAt.toISOString();
      time.textContent = clock.format(sentAt);
      time.title = sentAt.toLocaleString("vi-VN");
      const body = document.createElement("p");
      body.className = "chat-body";
      body.textContent = text;
      meta.append(label,time);
      row.append(meta,body);
      rows.append(row);
      after = id;
    }
    log.append(rows);
    const expandedHeight = log.scrollHeight;
    while (log.childElementCount > 180) log.firstElementChild.remove();
    if (atBottom) log.scrollTop = log.scrollHeight;
    else if (expandedHeight > log.scrollHeight) log.scrollTop -= expandedHeight-log.scrollHeight;
    empty.hidden = log.childElementCount > 0;
  }

  function schedule(delay) {
    clearTimeout(timer);
    if (!room.inert && onScreen && !document.hidden) timer = setTimeout(sync,delay);
  }

  function connection(state, label) {
    status.dataset.state = state;
    if (status.textContent !== label) status.textContent = label;
  }

  async function sync() {
    if (syncing || room.inert || document.hidden || !onScreen) return;
    syncing = true;
    let next = 3000+Math.random()*800;
    try {
      const response = await fetch(endpoint+(after ? "?after="+encodeURIComponent(after) : ""), {
        signal:AbortSignal.timeout(7500)
      });
      const data = await response.json();
      if (data.error === "unconfigured") {
        connected = false;
        connection("unavailable", "Phòng chat chưa được kết nối.");
        next = 30000;
      } else {
        if (!response.ok) throw new Error("Chat unavailable");
        await identified;
        append(data.messages);
        if (!after) after = "0-0";
        connected = true;
        failures = 0;
        connection("connected", "Đã kết nối");
        // A quiet room is polled less and less often, down to every 15 seconds.
        idle = data.messages.length ? 0 : Math.min(idle+1,8);
        next = data.more ? 0 : Math.min(15000,next*1.25**idle);
      }
    } catch {
      connected = false;
      connection("connecting", "Đang thử kết nối lại…");
      next = Math.min(30000,3000*2**Math.min(++failures,4));
    } finally {
      syncing = false;
      send.disabled = sending || !connected;
      schedule(next);
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const draft = input.value;
    const text = draft.trim();
    const nickname = name.value.trim();
    if (!text || sending || !connected) return;
    if (!retry || retry.text !== text || retry.name !== nickname) {
      retry = { client, nonce:crypto.randomUUID(), name:nickname, text };
    }
    try { localStorage.setItem("chotto-chat-name",nickname); } catch {}
    sending = true;
    send.disabled = true;
    notice.textContent = "";
    send.textContent = "Đang gửi…";
    try {
      const response = await fetch(endpoint, {
        method:"POST", headers:{ "Content-Type":"application/json" },
        body:JSON.stringify(retry), signal:AbortSignal.timeout(7500)
      });
      const refusal = response.status === 400 || response.status === 429
        ? (await response.json()).error : "";
      if (Object.hasOwn(rejected,refusal)) {
        notice.textContent = rejected[refusal];
      } else if (response.status === 429) {
        notice.textContent = "Bạn gửi hơi nhanh. Thử lại sau vài giây.";
      } else {
        if (!response.ok) throw new Error("Send failed");
        const { id } = await response.json();
        if (!/^\d{1,19}-\d{1,19}$/.test(id)) throw new Error("Missing message ID");
        if (input.value === draft) input.value = "";
        retry = null;
        log.scrollTop = log.scrollHeight;
        idle = 0;
        schedule(0);
      }
    } catch {
      notice.textContent = "Chưa xác nhận đã gửi. Bấm Gửi để thử lại.";
    } finally {
      sending = false;
      send.disabled = !connected;
      send.textContent = "Gửi";
    }
  });

  function setOpen(open, instant) {
    room.toggleAttribute("data-instant", instant);
    toggle.setAttribute("aria-expanded",String(open));
    toggle.textContent = open ? "Đóng phòng chat" : "Mở phòng chat";
    if (open) {
      room.inert = false;
      idle = 0;
      close.focus({ preventScroll:true });
    } else {
      toggle.focus({ preventScroll:true });
      room.inert = true;
    }
    schedule(0);
  }

  toggle.addEventListener("click",(event)=>setOpen(room.inert,event.detail === 0));
  close.addEventListener("click",(event)=>setOpen(false,event.detail === 0));
  document.addEventListener("keydown",(event)=>{
    if (event.key === "Escape" && !event.isComposing && !room.inert && !event.defaultPrevented) {
      event.preventDefault();
      setOpen(false,true);
    }
  });
  document.addEventListener("visibilitychange",()=>schedule(0));
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(([entry]) => {
      onScreen = entry.isIntersecting;
      schedule(0);
    }).observe(room);
  } else {
    onScreen = true;
    schedule(0);
  }
})();
