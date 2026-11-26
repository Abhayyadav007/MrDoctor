(() => {
  const log = document.getElementById("staff-chat-log");
  const form = document.getElementById("staff-chat-form");
  const input = document.getElementById("staff-chat-input");
  const status = document.getElementById("staff-chat-status");
  const typing = document.getElementById("staff-typing");
  if (!log || !form || !input || !status || !typing) return;

  const myId = Number(log.dataset.userId);
  const socket = new WebSocket(log.dataset.wsUrl);
  let typingTimer;
  const scrollToLatest = () => { log.scrollTop = log.scrollHeight; };
  const addMessage = (message) => {
    document.getElementById("staff-chat-empty")?.remove();
    const row = document.createElement("div");
    row.className = `staff-message${message.mine ? " staff-message-own" : ""}`;
    const bubble = document.createElement("div");
    bubble.className = "staff-message-bubble";
    const author = document.createElement("div");
    author.className = "staff-message-author";
    author.textContent = message.sender;
    const body = document.createElement("div");
    body.className = "staff-message-body";
    body.textContent = message.body;
    const time = document.createElement("time");
    const created = new Date(message.created_at);
    time.dateTime = created.toISOString();
    time.textContent = created.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
    bubble.append(author, body, time);
    row.append(bubble);
    log.append(row);
    scrollToLatest();
  };

  socket.addEventListener("open", () => { status.textContent = "Connected"; input.disabled = false; });
  socket.addEventListener("close", () => { status.textContent = "Disconnected. Refresh to reconnect."; input.disabled = true; });
  socket.addEventListener("error", () => { status.textContent = "Connection error"; });
  socket.addEventListener("message", (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "message") {
      addMessage({ ...data, mine: data.sender_id === myId });
      typing.textContent = "";
    } else if (data.type === "typing" && data.sender_id !== myId) {
      typing.textContent = data.active ? "Typing…" : "";
    } else if (data.type === "error") {
      status.textContent = data.message;
    }
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const body = input.value.trim();
    if (!body || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ type: "message", body }));
    input.value = "";
    socket.send(JSON.stringify({ type: "typing", active: false }));
  });
  input.addEventListener("input", () => {
    if (socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ type: "typing", active: true }));
    window.clearTimeout(typingTimer);
    typingTimer = window.setTimeout(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "typing", active: false }));
    }, 900);
  });
  scrollToLatest();
})();
