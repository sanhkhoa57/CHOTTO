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
  name.placeholder = "Khách " + client.slice(0,4).toUpperCase();

  let after = "", timer, syncing = false, sending = false, connected = false;
  let onScreen = false, failures = 0, retry = null;

  function append(messages) {
    const atBottom = log.scrollHeight-log.scrollTop-log.clientHeight < 32;
    const previousHeight = log.scrollHeight;
    const rows = document.createDocumentFragment();
    for (const { id, client: author, name: nickname, text } of messages) {
      const row = document.createElement("article");
      row.className = author === client ? "chat-message mine" : "chat-message";
      const meta = document.createElement("div");
      meta.className = "chat-meta";
      const label = document.createElement("strong");
      label.textContent = author === client ? nickname + " (bạn)" : nickname;
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
        status.textContent = "Phòng chat chưa được kết nối.";
        next = 30000;
      } else {
        if (!response.ok) throw new Error("Chat unavailable");
        append(data.messages);
        if (!after) after = "0-0";
        connected = true;
        failures = 0;
        if (status.textContent !== "Đã kết nối") status.textContent = "Đã kết nối";
        if (data.more) next = 0;
      }
    } catch {
      connected = false;
      status.textContent = "Đang thử kết nối lại…";
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
      if (response.status === 429) {
        notice.textContent = "Bạn gửi hơi nhanh. Thử lại sau vài giây.";
      } else {
        if (!response.ok) throw new Error("Send failed");
        const { id } = await response.json();
        if (!/^\d{1,19}-\d{1,19}$/.test(id)) throw new Error("Missing message ID");
        if (input.value === draft) input.value = "";
        retry = null;
        log.scrollTop = log.scrollHeight;
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

  function setOpen(open) {
    toggle.setAttribute("aria-expanded",String(open));
    if (open) {
      room.inert = false;
      close.focus({ preventScroll:true });
    } else {
      toggle.focus({ preventScroll:true });
      room.inert = true;
    }
    schedule(0);
  }

  toggle.addEventListener("click",()=>setOpen(room.inert));
  close.addEventListener("click",()=>setOpen(false));
  document.addEventListener("keydown",(event)=>{
    if (event.key === "Escape" && !room.inert && !event.defaultPrevented) {
      event.preventDefault();
      setOpen(false);
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
