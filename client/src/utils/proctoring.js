// Pure logic for monitored tests: confirmation rules, speech detection and the
// wording of warnings. No browser APIs here, so it's unit-tested with `node --test`.
// The server decides what each confirmed event costs; this decides what to report.

export const VIOLATION_TYPES = ["screen_switch", "voice", "face", "phone"];

export const VIOLATION_LABELS = {
  screen_switch: "Full screen",
  voice: "Speech",
  face: "Camera",
  phone: "Phone",
  technical: "Technical",
};

const DETAIL_TEXT = {
  fullscreen_exit: "You left full-screen mode.",
  tab_hidden: "You switched to another tab or app.",
  left_page: "You left or reloaded the test page.",
  sustained_speech: "Talking was detected (sustained speech).",
  no_face: "No one was visible in the camera.",
  multiple_faces: "More than one person was visible in the camera.",
  camera_unavailable: "Your camera stayed off.",
  phone_detected: "A possible mobile phone was detected.",
};

export const DETAIL_LABELS = {
  fullscreen_exit: "Left full screen",
  tab_hidden: "Switched tab or app",
  left_page: "Left or reloaded the page",
  sustained_speech: "Sustained speech",
  no_face: "No one visible",
  multiple_faces: "More than one person",
  camera_unavailable: "Camera off",
  phone_detected: "Phone detected",
  camera_interrupted: "Camera disconnected",
  microphone_interrupted: "Microphone disconnected",
  camera_checks_failing: "Camera checks failing",
  monitoring_resumed: "Monitoring resumed",
  page_reloaded: "Page reloaded",
};

export const REASON_TEXT = {
  STUDENT_SUBMITTED: "You submitted the test.",
  TIME_LIMIT: "Time ran out, so your saved answers were submitted automatically.",
  SCREEN_SWITCH_LIMIT: "Your test was submitted automatically because you left full screen too many times.",
  VOICE_VIOLATION_LIMIT: "Your test was submitted automatically because talking was detected too many times.",
  FACE_VIOLATION_LIMIT: "Your test was submitted automatically because of too many camera violations.",
  PHONE_DETECTION_LIMIT: "Your test was submitted automatically because a phone was detected too many times.",
};

export const LIMIT_REASONS = new Set([
  "SCREEN_SWITCH_LIMIT",
  "VOICE_VIOLATION_LIMIT",
  "FACE_VIOLATION_LIMIT",
  "PHONE_DETECTION_LIMIT",
]);

/** The checks a test runs, in display order. */
export const activeChecks = (monitoring) =>
  VIOLATION_TYPES.filter((type) =>
    type === "screen_switch"
      ? monitoring?.fullscreenRequired
      : type === "voice"
        ? monitoring?.microphoneRequired
        : type === "face"
          ? monitoring?.cameraRequired
          : monitoring?.phoneDetection,
  );

export const reasonLabel = (reason) =>
  ({
    SCREEN_SWITCH_LIMIT: "Full-screen limit",
    VOICE_VIOLATION_LIMIT: "Speech limit",
    FACE_VIOLATION_LIMIT: "Camera limit",
    PHONE_DETECTION_LIMIT: "Phone limit",
    TIME_LIMIT: "Time ran out",
    STUDENT_SUBMITTED: "Submitted",
  })[reason] ?? reason;

/** The create form's starting rules (the server applies the same defaults). */
export const DEFAULT_MONITORING = {
  enabled: true,
  fullscreenRequired: true,
  cameraRequired: true,
  microphoneRequired: true,
  phoneDetection: true,
  maxScreenSwitches: 3,
  maxVoiceViolations: 5,
  maxFaceViolations: 5,
  facePenalty: 5,
  maxPhoneViolations: 3,
};

/** Form values for MonitoringSettings from a test's `monitoring` (API shape).
 * Always proctored: saving the form turns proctoring on for a test created before it existed. */
export const monitoringFormValues = (m) => ({
  enabled: true,
  fullscreenRequired: m.fullscreenRequired,
  cameraRequired: m.cameraRequired,
  microphoneRequired: m.microphoneRequired,
  phoneDetection: m.phoneDetection,
  maxScreenSwitches: m.limits.screen_switch,
  maxVoiceViolations: m.limits.voice,
  maxFaceViolations: m.limits.face,
  facePenalty: m.facePenalty,
  maxPhoneViolations: m.limits.phone,
});

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** Message parts for the warning shown after a confirmed violation. */
export const describeViolation = ({ type, detail, count, limit, penalty = 0, totalPenalty = 0 }) => {
  const parts = {
    title: VIOLATION_LABELS[type] ?? "Proctoring",
    message: DETAIL_TEXT[detail] ?? "A proctoring rule was broken.",
    progress: limit > 0 ? `This is violation ${count} of ${limit}.` : `Violations so far: ${count}.`,
    deduction:
      penalty > 0 ? `${plural(penalty, "mark")} deducted. Current score adjustment: −${totalPenalty} marks.` : null,
    consequence: null,
  };
  if (limit > 0) {
    const left = limit - count;
    parts.consequence =
      left <= 0
        ? "Your test is being submitted."
        : left === 1
          ? "One more will automatically submit your test."
          : `${left} more will automatically submit your test.`;
  }
  return parts;
};

/* ---------------------------------------------------------------------------- */
/* Camera evidence                                                              */
/* ---------------------------------------------------------------------------- */

/** Used until the server's `monitoring.detection` arrives (same values as its defaults). */
export const DEFAULT_DETECTION = {
  frameIntervalMs: 2000,
  absence: { window: 12000, positives: 5 },
  multiple: { window: 10000, positives: 4 },
  phone: { window: 10000, positives: 3 },
  clearRatio: 0.2,
  cooldownMs: 60000,
  cameraGraceMs: 30000,
};

export const detectionConfig = (detection) => ({
  ...DEFAULT_DETECTION,
  ...detection,
  absence: { ...DEFAULT_DETECTION.absence, ...detection?.absence },
  multiple: { ...DEFAULT_DETECTION.multiple, ...detection?.multiple },
  phone: { ...DEFAULT_DETECTION.phone, ...detection?.phone },
});

/**
 * Evidence for one condition across recent camera checks. A condition is
 * confirmed when at least `positives` checks in the last `window` ms showed it,
 * so one bad frame (blur, a hand over the face) never counts, and one good frame
 * in the middle of a real problem doesn't reset it. Old checks age out (decay).
 *
 * An incident is reported once when confirmed, then again every `cooldownMs`
 * while it carries on. It ends when no more than `clearRatio` of the window's
 * checks show the condition; after that a new incident can be reported.
 *
 * push(true | false, now): the condition was / wasn't seen in a check.
 * push(null, now): the check failed; it is not evidence either way.
 * Returns { state: "clear" | "suspected" | "confirmed", report, ratio }.
 */
export const createEvidenceTracker = ({ window, positives, clearRatio = 0.2, cooldownMs = 60000 }) => {
  let samples = [];
  let active = false;
  let reportedAt = null;
  return {
    push(hit, now) {
      samples = samples.filter((s) => now - s.at < window);
      if (hit !== null && hit !== undefined) samples.push({ at: now, hit: Boolean(hit) });
      const hits = samples.reduce((n, s) => n + (s.hit ? 1 : 0), 0);
      const ratio = samples.length ? hits / samples.length : 0;
      if (active && ratio <= clearRatio) active = false; // the incident is over
      let report = false;
      if (hits >= positives) {
        if (!active) {
          active = true;
          report = true;
        } else if (now - reportedAt >= cooldownMs) {
          report = true; // still going: count it again
        }
        if (report) reportedAt = now;
      }
      const state = active ? "confirmed" : hits > 0 ? "suspected" : "clear";
      return { state, report, ratio: Math.round(ratio * 100) / 100 };
    },
    reset() {
      samples = [];
      active = false;
      reportedAt = null;
    },
  };
};

/**
 * Turns each camera check into states and confirmed incidents, for scheduled
 * tests, practice tests and AI interviews alike. `push(result, now)` takes a
 * check from the server (or null when the check failed) and returns
 * { face, phone, events }:
 * - face: "ok" | "away" | "absent-suspected" | "absent" | "multiple-suspected" | "multiple"
 *   ("away" means the student is there but not facing the camera; it is shown,
 *   never counted)
 * - phone: "none" | "suspected" | "detected"
 * - events: [{ type, detail, confidence }] to report (each incident once)
 */
export const createCameraEvidence = (detection, { phone: checkPhone = true } = {}) => {
  const config = detectionConfig(detection);
  const shared = {
    clearRatio: config.clearRatio,
    cooldownMs: config.cooldownMs,
  };
  const absence = createEvidenceTracker({ ...config.absence, ...shared });
  const multiple = createEvidenceTracker({ ...config.multiple, ...shared });
  const phone = createEvidenceTracker({ ...config.phone, ...shared });
  return {
    push(result, now) {
      const ok = result && typeof result.people === "number";
      const a = absence.push(ok ? result.people === 0 : null, now);
      const m = multiple.push(ok ? result.people >= 2 : null, now);
      const p = checkPhone ? phone.push(ok ? Boolean(result.phone) : null, now) : { state: "clear", report: false };
      const events = [];
      if (a.report) events.push({ type: "face", detail: "no_face", confidence: a.ratio });
      if (m.report)
        events.push({
          type: "face",
          detail: "multiple_faces",
          confidence: result?.peopleConfidence || m.ratio,
        });
      if (p.report)
        events.push({
          type: "phone",
          detail: "phone_detected",
          confidence: result?.phoneConfidence || p.ratio,
        });
      const face =
        m.state === "confirmed"
          ? "multiple"
          : a.state === "confirmed"
            ? "absent"
            : ok && result.people >= 2
              ? "multiple-suspected"
              : ok && result.people === 0
                ? "absent-suspected"
                : ok && result.lookingAway
                  ? "away"
                  : "ok";
      const phoneState =
        p.state === "confirmed"
          ? "detected"
          : p.state === "suspected" || (ok && result.phoneSuspected)
            ? "suspected"
            : "none";
      return { face, phone: checkPhone ? phoneState : "none", events };
    },
    reset() {
      absence.reset();
      multiple.reset();
      phone.reset();
    },
  };
};

/**
 * Leaving full screen, hiding the tab and unloading the page often fire together
 * for one action; count them as one screen switch. Returning to full screen
 * ends that absence (reset), so the next exit counts on its own.
 */
export const createSwitchGate = (windowMs = 3000) => {
  let last = -Infinity;
  return {
    shouldReport(now) {
      if (now - last < windowMs) return false;
      last = now;
      return true;
    },
    reset() {
      last = -Infinity;
    },
  };
};

/* ---------------------------------------------------------------------------- */
/* Speech detection                                                             */
/* ---------------------------------------------------------------------------- */

// Voice energy sits mostly between ~300 Hz and ~3.4 kHz; typing and clicks are
// short broadband bursts, hums are narrow and steady.
const SPEECH_LOW_HZ = 300;
const SPEECH_HIGH_HZ = 3400;

/**
 * Features of one ~100 ms audio frame.
 * `freqDb`: AnalyserNode.getFloatFrequencyData output (dB per bin);
 * `timeData`: getFloatTimeDomainData output (-1..1).
 */
export const audioFeatures = (freqDb, timeData, sampleRate) => {
  let sumSquares = 0;
  for (let i = 0; i < timeData.length; i++) sumSquares += timeData[i] * timeData[i];
  const rms = Math.sqrt(sumSquares / timeData.length);

  const binHz = sampleRate / 2 / freqDb.length;
  let total = 0;
  let speech = 0;
  let logSum = 0;
  let count = 0;
  for (let i = 1; i < freqDb.length; i++) {
    const db = Number.isFinite(freqDb[i]) ? freqDb[i] : -160;
    const power = 10 ** (db / 10);
    total += power;
    const hz = i * binHz;
    if (hz >= SPEECH_LOW_HZ && hz <= SPEECH_HIGH_HZ) {
      speech += power;
      logSum += Math.log(power + 1e-20);
      count += 1;
    }
  }
  const mean = count ? speech / count : 0;
  // Spectral flatness in the speech band: ~1 for noise, low for voiced sound.
  const flatness = count && mean > 0 ? Math.exp(logSum / count) / mean : 1;
  return { rms, speechBandRatio: total > 0 ? speech / total : 0, flatness };
};

/** Tracks the room's background level; adapts down fast and up slowly. */
export const createNoiseFloor = (initial = 0.01) => {
  let floor = initial;
  return {
    update(rms) {
      floor = rms < floor ? floor * 0.9 + rms * 0.1 : floor * 0.998 + rms * 0.002;
      floor = Math.max(floor, 0.002);
      return floor;
    },
    get value() {
      return floor;
    },
  };
};

/** Whether one frame sounds like someone speaking (well above the room, voice-shaped). */
export const isSpeechFrame = ({ rms, speechBandRatio, flatness }, noiseFloor) =>
  rms > Math.max(noiseFloor * 3, 0.01) && speechBandRatio > 0.55 && flatness < 0.45;

/**
 * Confirms sustained speech: at least `threshold` of the frames in a sliding
 * window (default 4 s of 100 ms frames) are speech. A cough or a burst of typing
 * can't fill the window. After a report it waits for quiet, or `repeatMs`.
 */
export const createSpeechDetector = ({ windowSize = 40, threshold = 0.6, quiet = 0.2, repeatMs = 20000 } = {}) => {
  const frames = [];
  let speechCount = 0;
  let reportedAt = null;
  return {
    push(isSpeech, now) {
      frames.push(isSpeech);
      if (isSpeech) speechCount += 1;
      if (frames.length > windowSize && frames.shift()) speechCount -= 1;
      if (frames.length < windowSize) return null;
      const ratio = speechCount / windowSize;
      if (ratio < quiet) reportedAt = null; // the episode is over
      if (ratio >= threshold && (reportedAt === null || now - reportedAt >= repeatMs)) {
        reportedAt = now;
        return { confidence: Math.round(ratio * 100) / 100 };
      }
      return null;
    },
  };
};

const FACE_TEXT = {
  ok: ["ok", "Just you"],
  away: ["notice", "Looking away"],
  "absent-suspected": ["notice", "Checking: no one visible"],
  absent: ["warn", "No one visible"],
  "multiple-suspected": ["notice", "Checking: more than one person"],
  multiple: ["warn", "More than one person"],
};
const PHONE_TEXT = {
  none: ["ok", "No phone detected"],
  suspected: ["notice", "Phone suspected"],
  detected: ["warn", "Phone detected"],
};

/**
 * Live rows for the Proctoring panel: [{ key, label, state, text }], state being
 * "ok" | "notice" | "warn" | "checking". `lastCheck` is the latest camera check
 * with the evidence states from createCameraEvidence ({ face, phone }).
 */
export const proctorStatuses = ({ monitoring, lastCheck, cameraLive, micLive, fullscreen }) => {
  const rows = [];
  const row = ([state, text]) => ({ state, text });
  const warn = (text) => ({ state: "warn", text });
  const checking = { state: "checking", text: "Checking" };
  if (monitoring?.cameraRequired) {
    rows.push({
      key: "people",
      label: "People in frame",
      ...(!cameraLive
        ? warn("Camera off")
        : lastCheck?.face
          ? row(FACE_TEXT[lastCheck.face] ?? FACE_TEXT.ok)
          : checking),
    });
  }
  if (monitoring?.phoneDetection) {
    rows.push({
      key: "phone",
      label: "Phone",
      ...(!cameraLive
        ? warn("Camera off")
        : lastCheck?.phone
          ? row(PHONE_TEXT[lastCheck.phone] ?? PHONE_TEXT.none)
          : checking),
    });
  }
  if (monitoring?.microphoneRequired) {
    rows.push({
      key: "microphone",
      label: "Microphone",
      ...(micLive ? row(["ok", "Listening"]) : warn("Disconnected")),
    });
  }
  if (monitoring?.fullscreenRequired) {
    rows.push({
      key: "fullscreen",
      label: "Full screen",
      ...(fullscreen ? row(["ok", "On"]) : warn("Off")),
    });
  }
  return rows;
};

/** The exam top bar's count chips for a test's active checks: [{ key, count, limit }]. */
export const checkChips = (monitoring) =>
  activeChecks(monitoring).map((key) => ({
    key,
    count: monitoring?.counts?.[key] ?? 0,
    limit: monitoring?.limits?.[key] ?? 0,
  }));

/** A unique id per confirmed event, so retries are recognised by the server. */
export const newEventId = () =>
  globalThis.crypto?.randomUUID
    ? globalThis.crypto.randomUUID().replaceAll("-", "")
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
