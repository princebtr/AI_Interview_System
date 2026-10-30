import { useEffect, useLayoutEffect, useRef, useState } from "react";
import api from "../utils/axios";
import { API_CONFIG } from "../config/api";
import {
  audioFeatures,
  createCameraEvidence,
  createNoiseFloor,
  createSpeechDetector,
  createSwitchGate,
  detectionConfig,
  isSpeechFrame,
  newEventId,
} from "../utils/proctoring";

const MULTIPART = { headers: { "Content-Type": "multipart/form-data" } };
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/* ---------------------------------------------------------------------------- */
/* Full screen and media helpers                                                */
/* ---------------------------------------------------------------------------- */

export const fullscreenSupported = () =>
  typeof document !== "undefined" && Boolean(document.fullscreenEnabled || document.webkitFullscreenEnabled);

export const isFullscreen = () => Boolean(document.fullscreenElement || document.webkitFullscreenElement);

/** Must be called from a click (the browser requires a user gesture). */
export const enterFullscreen = async () => {
  const root = document.documentElement;
  if (root.requestFullscreen) await root.requestFullscreen({ navigationUI: "hide" });
  else if (root.webkitRequestFullscreen) root.webkitRequestFullscreen();
  else throw new Error("Full screen isn't supported in this browser");
  if (!isFullscreen()) throw new Error("Full screen was blocked");
};

export const exitFullscreen = () => {
  if (!isFullscreen()) return;
  const exit = document.exitFullscreen ?? document.webkitExitFullscreen;
  Promise.resolve(exit?.call(document)).catch(() => {});
};

export const requestMedia = ({ camera, microphone }) => {
  if (!navigator.mediaDevices?.getUserMedia) {
    const error = new Error("Camera and microphone access isn't available in this browser");
    error.name = "NotSupportedError";
    return Promise.reject(error);
  }
  return navigator.mediaDevices.getUserMedia({
    video: camera ? { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" } : false,
    // Browser noise suppression keeps voices and removes steady noise, which helps
    // speech detection; automatic gain would make loudness meaningless.
    audio: microphone
      ? {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: false,
        }
      : false,
  });
};

export const mediaErrorMessage = (error) => {
  switch (error?.name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Access was blocked. Allow the camera and microphone for this site in your browser's address bar, then try again.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No camera or microphone was found. Connect one and try again.";
    case "NotReadableError":
      return "Your camera or microphone is being used by another app. Close it and try again.";
    default:
      return error?.message || "Couldn't start the camera or microphone.";
  }
};

export const stopStream = (stream) => stream?.getTracks().forEach((track) => track.stop());

/**
 * JPEG frames (at most 640 px wide) from a camera stream, through a <video> that
 * isn't in the page, so capture never depends on what is on screen.
 */
export const createFrameGrabber = (stream) => {
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.srcObject = stream?.getVideoTracks().length ? stream : null;
  video.play?.().catch(() => {});
  const canvas = document.createElement("canvas");
  return {
    async grab() {
      if (!video.srcObject || video.readyState < 2 || !video.videoWidth) return null;
      const scale = Math.min(1, 640 / video.videoWidth);
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);
      canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
      return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.7));
    },
    stop() {
      video.pause();
      video.srcObject = null;
    },
  };
};

/* ---------------------------------------------------------------------------- */
/* Monitoring while the test runs                                               */
/* ---------------------------------------------------------------------------- */

// One key per proctored sitting, e.g. "/me/tests/<id>" or "/ai/practice/<quizId>".
const leaveKey = (basePath) => `cohortix:proctoring:${basePath}:left`;

/**
 * Reports a pending "left the page" event from a previous page load of this
 * test (a reload or a tab close mid-test). Same event id as the attempt made
 * while leaving, so the server counts it once whichever request arrives.
 */
export const takePendingLeave = (basePath) => {
  try {
    const raw = sessionStorage.getItem(leaveKey(basePath));
    sessionStorage.removeItem(leaveKey(basePath));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

/**
 * Runs the proctoring for one sitting while `running` is true and reports each
 * confirmed event. The server answers with the updated rules and counts, and
 * `submitted: true` once a limit has submitted the test.
 *
 * - `basePath`: the sitting's API path, with `/violations` and `/frame` under it
 *   (`/me/tests/<id>` for scheduled tests, `/ai/practice/<quizId>` for practice)
 * - `monitoring`: the rules and counts (as returned by the API)
 * - `stream`: the camera/microphone MediaStream (frames are captured from it directly,
 *   so the page can lay out its camera preview however it likes)
 * - `getSheet()`: latest { answers, review }, sent with every report so an
 *   automatic submission grades them
 * - `onReport(response)`, `onRejected(error)`: server results
 */
export const useProctoring = ({ basePath, running, monitoring, stream, getSheet, onReport, onRejected }) => {
  const [fullscreen, setFullscreen] = useState(() => isFullscreen());
  const [cameraLive, setCameraLive] = useState(true);
  const [micLive, setMicLive] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [lastCheck, setLastCheck] = useState(null);

  // Latest values for long-lived listeners and timers.
  const latest = useRef({});
  useLayoutEffect(() => {
    latest.current = {
      basePath,
      running,
      monitoring,
      getSheet,
      onReport,
      onRejected,
    };
  });
  const counts = useRef({});
  useEffect(() => {
    counts.current = monitoring?.counts ?? {};
  }, [monitoring?.counts]);
  const switchGate = useRef(createSwitchGate(3000));
  // stop() ends monitoring at once (before React re-renders), so leaving full
  // screen after submitting is never mistaken for a violation.
  const stopped = useRef(false);
  useEffect(() => {
    if (running) stopped.current = false;
  }, [running]);
  const live = () => latest.current.running && !stopped.current;

  const report = useRef(null);
  report.current = async ({ type, detail, confidence = null, eventId = newEventId() }) => {
    if (!live()) return;
    const { monitoring: rules } = latest.current;
    const limit = rules?.limits?.[type] ?? 0;
    // Reaching the limit submits the test: stop accepting answers right away.
    const final = type !== "technical" && limit > 0 && (counts.current[type] ?? 0) + 1 >= limit;
    if (final) setSubmitting(true);
    if (type !== "technical")
      counts.current = {
        ...counts.current,
        [type]: (counts.current[type] ?? 0) + 1,
      };
    if (type === "screen_switch") lastSwitch.current = { eventId, at: Date.now() };
    const body = {
      eventId,
      type,
      detail,
      confidence,
      ...latest.current.getSheet(),
    };
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        const { data } = await api.post(`${latest.current.basePath}/violations`, body);
        counts.current = data.monitoring?.counts ?? counts.current;
        latest.current.onReport?.(data);
        if (final && !data.submitted) setSubmitting(false);
        return;
      } catch (error) {
        const status = error.response?.status;
        if (status && status < 500 && status !== 429) {
          latest.current.onRejected?.(error); // e.g. already submitted or time is up
          setSubmitting(false);
          return;
        }
        await sleep(1000 * 2 ** attempt); // same eventId: the server ignores repeats
      }
    }
    setSubmitting(false);
  };
  const send = (event) => report.current(event);

  // A screen switch is sent after a short pause: if the page is unloading (a
  // reload also exits full screen), the pagehide handler sends it instead, as
  // "left_page", with the same id, on a request that survives the unload.
  const pendingSwitch = useRef(null);
  const lastSwitch = useRef(null);
  const screenSwitch = (detail) => {
    if (!switchGate.current.shouldReport(Date.now())) return;
    const eventId = newEventId();
    const timer = setTimeout(() => {
      pendingSwitch.current = null;
      send({ type: "screen_switch", detail, eventId });
    }, 600);
    pendingSwitch.current = { eventId, timer };
  };

  // Full screen and tab switches.
  useEffect(() => {
    if (!running || !monitoring?.fullscreenRequired) return undefined;
    const onChange = () => {
      const now = isFullscreen();
      setFullscreen(now);
      if (now) {
        // Back in full screen: the next exit (or leaving the page) is a new switch.
        switchGate.current.reset();
        lastSwitch.current = null;
      }
      if (!now && live()) screenSwitch("fullscreen_exit");
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden" && live()) screenSwitch("tab_hidden");
    };
    setFullscreen(isFullscreen());
    document.addEventListener("fullscreenchange", onChange);
    document.addEventListener("webkitfullscreenchange", onChange);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("fullscreenchange", onChange);
      document.removeEventListener("webkitfullscreenchange", onChange);
      document.removeEventListener("visibilitychange", onVisibility);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, monitoring?.fullscreenRequired]);

  // Leaving the page (reload, close, back button) is a screen switch. A keepalive
  // request reports it now; sessionStorage lets the next load report it if that fails.
  useEffect(() => {
    if (!running || !monitoring?.fullscreenRequired) return undefined;
    const leave = () => {
      if (!live()) return;
      const now = Date.now();
      let eventId;
      if (pendingSwitch.current) {
        clearTimeout(pendingSwitch.current.timer);
        eventId = pendingSwitch.current.eventId;
        pendingSwitch.current = null;
      } else if (lastSwitch.current && now - lastSwitch.current.at < 3000) {
        eventId = lastSwitch.current.eventId; // its request may be cut off by the unload: resend it
      } else if (switchGate.current.shouldReport(now)) {
        eventId = newEventId();
      } else {
        return;
      }
      const event = { eventId, type: "screen_switch", detail: "left_page" };
      try {
        sessionStorage.setItem(leaveKey(basePath), JSON.stringify(event));
      } catch {
        // Storage unavailable: the keepalive request below is the only report.
      }
      fetch(`${API_CONFIG.BASE_URL}${basePath}/violations`, {
        method: "POST",
        keepalive: true,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
        body: JSON.stringify({ ...event, ...latest.current.getSheet() }),
      }).catch(() => {});
    };
    window.addEventListener("pagehide", leave);
    return () => window.removeEventListener("pagehide", leave);
  }, [running, monitoring?.fullscreenRequired, basePath]);

  // Camera: a frame every couple of seconds is checked on the server (people,
  // faces, phones); incidents need evidence across several checks (see
  // createCameraEvidence). Timings come from the server's `monitoring.detection`.
  const detection = detectionConfig(monitoring?.detection);
  const frameEveryMs = detection.frameIntervalMs;
  useEffect(() => {
    if (!running || !monitoring?.cameraRequired) return undefined;
    const evidence = createCameraEvidence(latest.current.monitoring?.detection, {
      phone: Boolean(latest.current.monitoring?.phoneDetection),
    });
    const grabber = createFrameGrabber(stream);
    let busy = false;
    let failures = 0;
    let failingReported = false;
    const tick = async () => {
      if (busy) return; // never queue checks behind a slow one
      busy = true;
      try {
        const blob = await grabber.grab();
        if (!blob) return;
        const form = new FormData();
        form.append("image", blob, "frame.jpg");
        const { data } = await api.post(`${basePath}/frame`, form, MULTIPART);
        failures = 0;
        const now = Date.now();
        const { face, phone, events } = evidence.push(data, now);
        setLastCheck({ ...data, face, phone, at: now });
        events.forEach(send);
      } catch (error) {
        const status = error.response?.status;
        if (status === 429) return;
        if (status === 400) {
          latest.current.onRejected?.(error);
          return;
        }
        evidence.push(null, Date.now()); // a missed check never counts against the student
        failures += 1;
        if (failures >= 3 && !failingReported) {
          failingReported = true;
          send({ type: "technical", detail: "camera_checks_failing" });
        }
      } finally {
        busy = false;
      }
    };
    const timer = setInterval(tick, frameEveryMs);
    const first = setTimeout(tick, 500); // then every frameEveryMs (the server refuses checks under 1 s apart)
    return () => {
      clearInterval(timer);
      clearTimeout(first);
      grabber.stop();
    };
     
  }, [running, monitoring?.cameraRequired, basePath, stream, frameEveryMs]);

  // Camera or microphone disconnected: warn now; a camera off past the grace
  // period counts as a camera violation ("no one visible").
  useEffect(() => {
    if (!running || !stream) return undefined;
    const video = stream.getVideoTracks()[0];
    const audio = stream.getAudioTracks()[0];
    let cameraLostAt = monitoring?.cameraRequired && (!video || video.readyState === "ended") ? Date.now() : null;
    let lastCameraReport = 0;
    setCameraLive(!cameraLostAt);
    setMicLive(!monitoring?.microphoneRequired || audio?.readyState === "live");
    const onVideoEnded = () => {
      cameraLostAt = Date.now();
      setCameraLive(false);
      send({ type: "technical", detail: "camera_interrupted" });
    };
    const onAudioEnded = () => {
      setMicLive(false);
      send({ type: "technical", detail: "microphone_interrupted" });
    };
    if (monitoring?.cameraRequired) video?.addEventListener("ended", onVideoEnded);
    if (monitoring?.microphoneRequired) audio?.addEventListener("ended", onAudioEnded);
    const watch = setInterval(() => {
      const now = Date.now();
      const { cameraGraceMs, cooldownMs } = detectionConfig(latest.current.monitoring?.detection);
      if (cameraLostAt && now - cameraLostAt >= cameraGraceMs && now - lastCameraReport >= cooldownMs) {
        lastCameraReport = now;
        send({ type: "face", detail: "camera_unavailable" });
      }
    }, 2000);
    return () => {
      video?.removeEventListener("ended", onVideoEnded);
      audio?.removeEventListener("ended", onAudioEnded);
      clearInterval(watch);
    };
  }, [running, stream, monitoring?.cameraRequired, monitoring?.microphoneRequired]);

  // Microphone: speech detection runs entirely in the browser; no audio is sent or kept.
  useEffect(() => {
    const track = stream?.getAudioTracks()[0];
    if (!running || !monitoring?.microphoneRequired || !track) return undefined;
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) return undefined;
    const context = new Context();
    const source = context.createMediaStreamSource(new MediaStream([track]));
    const analyser = context.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0;
    source.connect(analyser);
    const freq = new Float32Array(analyser.frequencyBinCount);
    const time = new Float32Array(analyser.fftSize);
    const floor = createNoiseFloor();
    const detector = createSpeechDetector();
    context.resume?.().catch(() => {});
    const timer = setInterval(() => {
      analyser.getFloatFrequencyData(freq);
      analyser.getFloatTimeDomainData(time);
      const features = audioFeatures(freq, time, context.sampleRate);
      const speech = isSpeechFrame(features, floor.value);
      if (!speech) floor.update(features.rms); // learn the room from non-speech only
      const hit = detector.push(speech, Date.now());
      if (hit)
        send({
          type: "voice",
          detail: "sustained_speech",
          confidence: hit.confidence,
        });
    }, 100);
    return () => {
      clearInterval(timer);
      source.disconnect();
      context.close().catch(() => {});
    };
  }, [running, stream, monitoring?.microphoneRequired]);

  // Navigating away inside the app (e.g. the back button) also leaves the test.
  // Deferred so React StrictMode's dev-only remount doesn't count as leaving.
  const unmountTimer = useRef(null);
  useEffect(() => {
    clearTimeout(unmountTimer.current);
    return () => {
      unmountTimer.current = setTimeout(() => {
        if (live() && latest.current.monitoring?.fullscreenRequired) screenSwitch("left_page");
      }, 0);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stop = () => {
    stopped.current = true;
  };

  return {
    fullscreen,
    cameraLive,
    micLive,
    submitting,
    lastCheck,
    report: send,
    stop,
  };
};
