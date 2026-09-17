import { useCallback, useEffect, useRef, useState } from "react";
import type { AssistantChatResponse } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8001";

export type VoiceState = "off" | "connecting" | "on" | "error";

// Backend error codes (see gaf_realtime.py) mapped to something a customer
// actually understands -- these used to be shown verbatim (e.g. the raw
// string "realtime_session_unreachable"), which reads like a stack trace,
// not a message.
const VOICE_ERROR_MESSAGES: Record<string, string> = {
  realtime_not_configured: "Voice isn't set up in this environment yet.",
  realtime_session_timeout: "Couldn't reach the voice service in time. Please try again.",
  realtime_session_error: "The voice service rejected the request. Please try again shortly.",
  realtime_session_unreachable: "Couldn't reach the voice service. Check your connection and try again.",
  realtime_session_invalid_response: "The voice service returned something unexpected. Please try again.",
  session_failed: "Could not start the voice session. Please try again.",
};

function voiceErrorMessage(code: string): string {
  return VOICE_ERROR_MESSAGES[code] || "Could not start voice. Please try again.";
}

const MICROPHONE_TIMEOUT_MS = 15000;

function microphoneErrorMessage(err: unknown): string {
  if (!(err instanceof DOMException)) {
    return err instanceof Error ? err.message : "Could not access the microphone.";
  }
  if (err.name === "NotAllowedError" || err.name === "SecurityError") {
    return "Microphone permission was blocked. Allow microphone access for this site, then try again.";
  }
  if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
    return "No microphone was found. Connect a microphone, then try again.";
  }
  if (err.name === "NotReadableError" || err.name === "TrackStartError") {
    return "The microphone is already in use by another app. Close that app, then try again.";
  }
  return "Could not access the microphone. Check browser permissions, then try again.";
}

async function requestMicrophone(): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("This browser does not support microphone access on this page.");
  }

  let timedOut = false;
  let timeoutId = 0;
  const micPromise = navigator.mediaDevices
    .getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    })
    .then((stream) => {
      if (timedOut) stream.getTracks().forEach((track) => track.stop());
      return stream;
    })
    .catch((err) => {
      throw new Error(microphoneErrorMessage(err));
    });

  const timeoutPromise = new Promise<never>((_, reject) => {
    timeoutId = window.setTimeout(() => {
      timedOut = true;
      reject(new Error("Microphone permission timed out. Check the browser permission prompt, then try again."));
    }, MICROPHONE_TIMEOUT_MS);
  });

  try {
    return await Promise.race([micPromise, timeoutPromise]);
  } finally {
    window.clearTimeout(timeoutId);
  }
}

interface UseGafVoiceOptions {
  location?: string;
  onTranscript: (role: "user" | "assistant", text: string) => void;
  onToolResult: (result: AssistantChatResponse) => void;
}

interface VoiceSessionPayload {
  success: boolean;
  client_secret?: string | null;
  realtime_url?: string | null;
  error?: string | null;
  post_connect_update?: Record<string, unknown> | null;
  turn?: { urls: string[]; username: string; credential: string } | null;
}

/**
 * Same WebRTC-direct-to-Azure architecture as telecom-assistant's voice
 * mode: this backend only mints an ephemeral token and executes tool calls
 * -- audio itself flows browser <-> Azure Realtime API directly over the
 * peer connection. Simpler than telecom's own hook in one respect: GAF is
 * English-only, so there's no transcript-gated language-switch dance --
 * the server always auto-responds (create_response stays true), and
 * transcripts here are purely for display.
 */
export function useGafVoice({ location, onTranscript, onToolResult }: UseGafVoiceOptions) {
  const [state, setState] = useState<VoiceState>("off");
  const [hint, setHint] = useState("");
  const meterCanvasRef = useRef<HTMLCanvasElement | null>(null);

  const peerConnectionRef = useRef<RTCPeerConnection | null>(null);
  const dataChannelRef = useRef<RTCDataChannel | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null);
  const responseActiveRef = useRef(false);
  const pendingActionsRef = useRef<Array<() => void>>([]);
  const meterCleanupRef = useRef<(() => void) | null>(null);
  const locationRef = useRef(location);
  locationRef.current = location;

  const whenResponseFree = useCallback((action: () => void) => {
    if (responseActiveRef.current) {
      pendingActionsRef.current.push(action);
      return;
    }
    action();
  }, []);

  const startMicMeter = useCallback((stream: MediaStream) => {
    const canvas = meterCanvasRef.current;
    if (!canvas) return;
    const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
    const audioContext = new AudioCtx();
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    const ctx = canvas.getContext("2d")!;
    const dpr = window.devicePixelRatio || 1;
    const BARS = 12;
    const bars = new Array(BARS).fill(0);
    const barColor = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#c8102e";

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
    };
    resize();
    window.addEventListener("resize", resize);

    let rafId = 0;
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      const perBar = Math.floor(data.length / BARS);
      for (let b = 0; b < BARS; b++) {
        let sum = 0;
        const start = b * perBar;
        for (let i = 0; i < perBar; i++) {
          const v = (data[start + i] - 128) / 128;
          sum += v * v;
        }
        const level = Math.min(1, Math.sqrt(sum / perBar) * 4.5);
        bars[b] += (level - bars[b]) * 0.22;
      }
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      const gap = w / BARS;
      const barW = gap * 0.6;
      ctx.fillStyle = barColor;
      for (let b = 0; b < BARS; b++) {
        const amp = Math.max(0.12, bars[b]);
        const barH = amp * h;
        const x = b * gap + (gap - barW) / 2;
        const y = (h - barH) / 2;
        ctx.globalAlpha = 0.55 + amp * 0.45;
        ctx.beginPath();
        ctx.roundRect(x, y, barW, barH, barW / 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      rafId = requestAnimationFrame(tick);
    };
    tick();

    meterCleanupRef.current = () => {
      cancelAnimationFrame(rafId);
      audioContext.close();
      window.removeEventListener("resize", resize);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, []);

  const teardown = useCallback(() => {
    meterCleanupRef.current?.();
    meterCleanupRef.current = null;
    try {
      dataChannelRef.current?.close();
    } catch {
      // already closed
    }
    try {
      peerConnectionRef.current?.close();
    } catch {
      // already closed
    }
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    if (remoteAudioRef.current) {
      remoteAudioRef.current.pause();
      remoteAudioRef.current.srcObject = null;
      remoteAudioRef.current.remove();
    }
    dataChannelRef.current = null;
    peerConnectionRef.current = null;
    micStreamRef.current = null;
    remoteAudioRef.current = null;
    responseActiveRef.current = false;
    pendingActionsRef.current = [];
  }, []);

  const stopVoice = useCallback(() => {
    teardown();
    setState("off");
    setHint("");
  }, [teardown]);

  async function handleFunctionCall(evt: any) {
    let args: Record<string, unknown> = {};
    try {
      args = JSON.parse(evt.arguments || "{}");
    } catch {
      args = {};
    }
    let output: unknown;
    try {
      const body: Record<string, unknown> = { function_name: evt.name, ...args };
      if (evt.name === "handle_customer_request" && !("location" in args) && locationRef.current) {
        body.location = locationRef.current;
      }
      const res = await fetch(`${API_BASE_URL}/api/voice/tool`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result = await res.json();
      output = result.success ? result.data : { error: result.error || "tool_error" };
      if (result.success && evt.name === "handle_customer_request") {
        onToolResult(result.data as AssistantChatResponse);
      }
    } catch (err) {
      output = { error: "request_failed" };
    }
    const dc = dataChannelRef.current;
    if (!dc) return;
    dc.send(
      JSON.stringify({
        type: "conversation.item.create",
        item: { type: "function_call_output", call_id: evt.call_id, output: JSON.stringify(output) },
      })
    );
    whenResponseFree(() => {
      dataChannelRef.current?.send(JSON.stringify({ type: "response.create" }));
      responseActiveRef.current = true;
    });
  }

  function onRealtimeEvent(evt: any) {
    switch (evt.type) {
      case "input_audio_buffer.speech_started":
        setHint("Hearing you…");
        if (responseActiveRef.current && dataChannelRef.current) {
          pendingActionsRef.current = [];
          dataChannelRef.current.send(JSON.stringify({ type: "response.cancel" }));
        }
        return;
      case "input_audio_buffer.speech_stopped":
        setHint("Thinking…");
        return;
      case "conversation.item.input_audio_transcription.completed":
      case "conversation.item.audio_transcription.completed":
        if (evt.transcript) onTranscript("user", evt.transcript);
        return;
      case "output_audio_buffer.started":
        setHint("Speaking…");
        return;
      case "output_audio_buffer.stopped":
        setHint("Listening — just talk");
        return;
      case "response.output_audio_transcript.done":
      case "response.audio_transcript.done":
        if (evt.transcript) onTranscript("assistant", evt.transcript);
        return;
      case "response.function_call_arguments.done":
        void handleFunctionCall(evt);
        return;
      case "response.created":
        responseActiveRef.current = true;
        return;
      case "response.done":
        responseActiveRef.current = false;
        if (pendingActionsRef.current.length) {
          const next = pendingActionsRef.current.shift();
          next?.();
        }
        return;
      case "error": {
        const msg: string = evt.error?.message || "";
        if (/no active response/i.test(msg)) return;
        return;
      }
      default:
        return;
    }
  }

  const startVoice = useCallback(async () => {
    if (peerConnectionRef.current) return;
    setState("connecting");
    setHint("Starting session…");
    try {
      const sessionRes = await fetch(`${API_BASE_URL}/api/voice/session`, { method: "POST" });
      const session: VoiceSessionPayload = await sessionRes.json();
      if (!session.success || !session.client_secret || !session.realtime_url) {
        throw new Error(voiceErrorMessage(session.error || "session_failed"));
      }

      const iceServers: RTCIceServer[] = [{ urls: "stun:stun.l.google.com:19302" }];
      if (session.turn) {
        iceServers.push({ urls: session.turn.urls, username: session.turn.username, credential: session.turn.credential });
      }
      const peerConnection = new RTCPeerConnection({ iceServers });
      peerConnectionRef.current = peerConnection;

      const remoteAudio = new Audio();
      remoteAudio.autoplay = true;
      remoteAudio.style.display = "none";
      document.body.appendChild(remoteAudio);
      remoteAudioRef.current = remoteAudio;
      peerConnection.ontrack = (e) => {
        remoteAudio.srcObject = e.streams[0];
      };

      setHint("Requesting microphone…");
      const micStream = await requestMicrophone();
      micStreamRef.current = micStream;
      peerConnection.addTrack(micStream.getAudioTracks()[0]);
      startMicMeter(micStream);

      const dataChannel = peerConnection.createDataChannel("realtime-channel");
      dataChannelRef.current = dataChannel;
      dataChannel.addEventListener("open", () => {
        setState("on");
        setHint("Listening — just talk");
        if (session.post_connect_update) {
          dataChannel.send(JSON.stringify(session.post_connect_update));
        }
      });
      dataChannel.addEventListener("message", (e) => onRealtimeEvent(JSON.parse(e.data)));
      dataChannel.addEventListener("close", () => stopVoice());

      const offer = await peerConnection.createOffer();
      await peerConnection.setLocalDescription(offer);
      const sdpRes = await fetch(session.realtime_url, {
        method: "POST",
        body: offer.sdp,
        headers: { Authorization: `Bearer ${session.client_secret}`, "Content-Type": "application/sdp" },
      });
      if (!sdpRes.ok) throw new Error(`SDP exchange failed: ${sdpRes.status}`);
      await peerConnection.setRemoteDescription({ type: "answer", sdp: await sdpRes.text() });
    } catch (err) {
      teardown();
      setState("error");
      setHint(err instanceof Error ? err.message : "Could not start voice");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startMicMeter, stopVoice, teardown]);

  useEffect(() => () => teardown(), [teardown]);

  return { state, hint, startVoice, stopVoice, meterCanvasRef };
}
