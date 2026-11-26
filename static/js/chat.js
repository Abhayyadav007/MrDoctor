(() => {
  const cfg = window.CaseChat;
  const messagesEl = document.getElementById("chatMessages");
  const form = document.getElementById("chatForm");
  const input = document.getElementById("messageInput");
  const presence = document.getElementById("presence");
  const typing = document.getElementById("typingIndicator");
  const callBanner = document.getElementById("callBanner");
  const callState = document.getElementById("callState");
  const incoming = document.getElementById("incomingCall");
  const videoStage = document.getElementById("videoStage");
  const remoteVideo = document.getElementById("remoteVideo");
  const remoteAudio = document.getElementById("remoteAudio");
  const localVideo = document.getElementById("localVideo");
  const rtcConfig = {iceServers: [{urls: "stun:stun.l.google.com:19302"}]};
  let socket, peerConnection, localStream, callId = null, incomingCall = null, callingPending = false;
  let audioOnly = false, initiator = false, muted = false, cameraOff = false, startedAt = null;
  let queuedCandidates = [], typingTimeout, ringTimeout, timerInterval;

  const send = (payload) => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(payload));
      return true;
    }
    return false;
  };
  const addNotice = (text) => {
    const node = document.createElement("div");
    node.className = "message-notice";
    node.textContent = text;
    messagesEl.append(node);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  };
  const addMessage = (item) => {
    const node = document.createElement("div");
    node.className = `message${Number(item.sender_id) === cfg.userId ? " mine" : ""}`;
    const text = document.createElement("div");
    text.textContent = item.text;
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const date = new Date(item.created_at);
    meta.textContent = `${item.sender} · ${date.toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"})}`;
    node.append(text, meta);
    messagesEl.append(node);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  };
  JSON.parse(document.getElementById("initial-messages").textContent).forEach(addMessage);

  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  socket = new WebSocket(`${scheme}//${location.host}/ws/cases/${cfg.caseId}/`);
  socket.onopen = () => { presence.textContent = "Connected"; };
  socket.onclose = (event) => {
    presence.textContent = event.code === 4403 ? "Not authorized" : "Offline";
    if (callId) finishCall("Chat connection lost");
  };
  socket.onerror = () => { presence.textContent = "Connection error"; };
  socket.onmessage = async (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "chat_message") addMessage(data);
    if (data.type === "presence" && data.user_id !== cfg.userId) presence.textContent = data.online ? "Online" : "Offline";
    if (data.type === "presence" && data.user_id !== cfg.userId && !data.online && callId) finishCall("Peer disconnected");
    if (data.type === "typing" && data.user_id !== cfg.userId) {
      typing.textContent = data.active ? `${cfg.peerName} is typing…` : "";
      clearTimeout(typingTimeout);
      if (data.active) typingTimeout = setTimeout(() => { typing.textContent = ""; }, 1800);
    }
    if (data.type === "call_invite") {
      callingPending = false;
      callId = data.call_id;
      audioOnly = data.audio_only;
      if (data.sender_id === cfg.userId) {
        initiator = true;
        ringTimeout = setTimeout(() => {
          if (callId) {
            send({type:"call_missed", call_id:callId});
            finishCall("No answer");
          }
        }, 30000);
        showCall("Ringing…");
      } else {
        incomingCall = {id:data.call_id, audioOnly:data.audio_only};
        document.getElementById("incomingName").textContent = `${data.sender} is calling`;
        incoming.classList.remove("d-none");
      }
    }
    if (data.type === "call_accept" && initiator && data.sender_id !== cfg.userId) {
      clearTimeout(ringTimeout);
      try {
        showCall("In call");
        await startPeer(true);
      } catch (error) {
        send({type:"call_end", call_id:callId});
        finishCall(`Could not access camera or microphone: ${error.message}`);
      }
    }
    if (data.type === "call_reject" && data.sender_id !== cfg.userId) finishCall("Call rejected");
    if (data.type === "call_reject" && data.sender_id === cfg.userId && incomingCall) finishCall("Call declined");
    if (data.type === "call_missed" && data.sender_id !== cfg.userId) finishCall("Missed call");
    if (data.type === "call_end" && data.sender_id !== cfg.userId) finishCall("Call ended");
    if (data.type === "offer" && data.sender_id !== cfg.userId) {
      try {
        await receiveOffer(data.payload);
      } catch (error) {
        addNotice(`Could not establish the call: ${error.message}`);
        send({type:"call_end", call_id:callId});
        finishCall("Call failed");
      }
    }
    if (data.type === "answer" && data.sender_id !== cfg.userId && peerConnection) {
      try {
        await peerConnection.setRemoteDescription(data.payload);
        await flushCandidates();
      } catch (error) {
        addNotice(`Could not process the call answer: ${error.message}`);
        send({type:"call_end", call_id:callId});
        finishCall("Call failed");
      }
    }
    if (data.type === "ice_candidate" && data.sender_id !== cfg.userId && data.payload) {
      if (peerConnection && peerConnection.remoteDescription) {
        try {
          await peerConnection.addIceCandidate(data.payload);
        } catch (error) {
          console.error("Unable to add WebRTC ICE candidate", error);
        }
      }
      else queuedCandidates.push(data.payload);
    }
    if (data.type === "error") addNotice(data.message);
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    send({type:"message", text});
    input.value = "";
    send({type:"typing", active:false});
  });
  input.addEventListener("input", () => {
    send({type:"typing", active:true});
    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => send({type:"typing", active:false}), 900);
  });
  document.getElementById("videoCall").addEventListener("click", () => beginCall(false));
  document.getElementById("audioCall").addEventListener("click", () => beginCall(true));

  function showCall(state) {
    callBanner.classList.remove("d-none");
    callState.textContent = state;
    if (state === "In call") {
      videoStage.classList.toggle("d-none", audioOnly);
      startedAt = Date.now();
      timerInterval = setInterval(() => {
        const seconds = Math.floor((Date.now() - startedAt) / 1000);
        document.getElementById("callTimer").textContent =
          `${String(Math.floor(seconds / 60)).padStart(2,"0")}:${String(seconds % 60).padStart(2,"0")}`;
      }, 1000);
    }
  }
  function beginCall(audio) {
    if (callId || callingPending) return;
    audioOnly = audio;
    initiator = true;
    if (!send({type:"call_start", audio_only:audio})) {
      addNotice("Chat is reconnecting. Wait until it shows Connected, then try the call again.");
      return;
    }
    callingPending = true;
  }
  async function startPeer(makeOffer) {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("This browser does not allow camera or microphone access here. Open the app on localhost or HTTPS.");
    }
    if (!localStream) localStream = await navigator.mediaDevices.getUserMedia({audio:true, video:!audioOnly});
    localVideo.srcObject = audioOnly ? null : localStream;
    peerConnection = new RTCPeerConnection(rtcConfig);
    localStream.getTracks().forEach((track) => peerConnection.addTrack(track, localStream));
    peerConnection.ontrack = async (event) => {
      const mediaElement = audioOnly ? remoteAudio : remoteVideo;
      mediaElement.srcObject = event.streams[0];
      try {
        await mediaElement.play();
      } catch (error) {
        addNotice(`Allow audio playback in your browser to hear the call: ${error.message}`);
      }
    };
    peerConnection.onicecandidate = (event) => {
      if (event.candidate) send({type:"ice_candidate", payload:event.candidate.toJSON()});
    };
    peerConnection.onconnectionstatechange = () => {
      if (peerConnection && ["failed","disconnected"].includes(peerConnection.connectionState)) {
        callState.textContent = "Connection interrupted";
      }
    };
    if (makeOffer) {
      const offer = await peerConnection.createOffer();
      await peerConnection.setLocalDescription(offer);
      send({type:"offer", payload:{type:peerConnection.localDescription.type, sdp:peerConnection.localDescription.sdp}});
    }
  }
  async function receiveOffer(offer) {
    if (!peerConnection) await startPeer(false);
    await peerConnection.setRemoteDescription(offer);
    await flushCandidates();
    const answer = await peerConnection.createAnswer();
    await peerConnection.setLocalDescription(answer);
    send({type:"answer", payload:{type:peerConnection.localDescription.type, sdp:peerConnection.localDescription.sdp}});
  }
  async function flushCandidates() {
    for (const candidate of queuedCandidates) await peerConnection.addIceCandidate(candidate);
    queuedCandidates = [];
  }
  document.getElementById("acceptCall").addEventListener("click", async () => {
    if (!incomingCall) return;
    callId = incomingCall.id;
    audioOnly = incomingCall.audioOnly;
    initiator = false;
    incoming.classList.add("d-none");
    try {
      await startPeer(false);
      send({type:"call_accept", call_id:callId});
      showCall("In call");
    } catch (error) {
      addNotice(`Could not access camera or microphone: ${error.message}`);
      send({type:"call_reject", call_id:callId});
      finishCall("Call unavailable");
    }
  });
  document.getElementById("rejectCall").addEventListener("click", () => {
    if (incomingCall) send({type:"call_reject", call_id:incomingCall.id});
    incomingCall = null;
    incoming.classList.add("d-none");
  });
  document.getElementById("endCall").addEventListener("click", () => {
    if (callId) send({type:"call_end", call_id:callId});
    finishCall("Call ended");
  });
  document.getElementById("muteMic").addEventListener("click", (event) => {
    muted = !muted;
    if (localStream) localStream.getAudioTracks().forEach((track) => { track.enabled = !muted; });
    event.currentTarget.innerHTML = `<i class="bi bi-mic${muted ? "-mute" : ""}"></i>`;
    document.getElementById("muteAudio").innerHTML = `<i class="bi bi-mic${muted ? "-mute" : ""}"></i>`;
  });
  document.getElementById("muteAudio").addEventListener("click", () => {
    muted = !muted;
    if (localStream) localStream.getAudioTracks().forEach((track) => { track.enabled = !muted; });
    document.getElementById("muteAudio").innerHTML = `<i class="bi bi-mic${muted ? "-mute" : ""}"></i>`;
    const videoMute = document.getElementById("muteMic");
    if (videoMute) videoMute.innerHTML = `<i class="bi bi-mic${muted ? "-mute" : ""}"></i>`;
  });
  document.getElementById("toggleCamera").addEventListener("click", (event) => {
    cameraOff = !cameraOff;
    if (localStream) localStream.getVideoTracks().forEach((track) => { track.enabled = !cameraOff; });
    event.currentTarget.innerHTML = `<i class="bi bi-camera-video${cameraOff ? "-off" : ""}"></i>`;
  });
  function finishCall(notice) {
    clearTimeout(ringTimeout);
    clearInterval(timerInterval);
    if (peerConnection) peerConnection.close();
    peerConnection = null;
    if (localStream) localStream.getTracks().forEach((track) => track.stop());
    localStream = null;
    remoteVideo.srcObject = null;
    remoteAudio.srcObject = null;
    localVideo.srcObject = null;
    callId = null;
    callingPending = false;
    incomingCall = null;
    incoming.classList.add("d-none");
    videoStage.classList.add("d-none");
    callBanner.classList.add("d-none");
    if (notice) addNotice(notice);
  }
})();
