// Run with `npm test` (node --test). No browser needed: this is the pure logic.
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  audioFeatures,
  createCameraEvidence,
  createEvidenceTracker,
  createNoiseFloor,
  createSpeechDetector,
  createSwitchGate,
  describeViolation,
  detectionConfig,
  isSpeechFrame,
  monitoringFormValues,
  newEventId,
  proctorStatuses,
} from "./proctoring.js";

const SAMPLE_RATE = 48000;
const BINS = 1024;
const binOf = (hz) => Math.round(hz / (SAMPLE_RATE / 2 / BINS));

// A synthetic analyser frame: harmonics at `peaksHz` above a quiet floor.
const spectrum = (peaksHz, { floorDb = -110, peakDb = -30 } = {}) => {
  const db = new Float32Array(BINS).fill(floorDb);
  for (const hz of peaksHz) db[binOf(hz)] = peakDb;
  return db;
};
const sine = (amplitude, n = 2048) => Float32Array.from({ length: n }, (_, i) => amplitude * Math.sin(i / 7));

describe("audio features", () => {
  it("recognises voiced sound in the speech band", () => {
    const features = audioFeatures(spectrum([220, 440, 660, 880, 1100, 1320]), sine(0.2), SAMPLE_RATE);
    assert.ok(features.speechBandRatio > 0.7, `ratio ${features.speechBandRatio}`);
    assert.ok(features.flatness < 0.2, `flatness ${features.flatness}`);
    assert.equal(isSpeechFrame(features, 0.01), true);
  });

  it("rejects broadband noise such as typing", () => {
    const noise = new Float32Array(BINS).fill(-40);
    const features = audioFeatures(noise, sine(0.3), SAMPLE_RATE);
    assert.ok(features.flatness > 0.9);
    assert.equal(isSpeechFrame(features, 0.01), false);
  });

  it("rejects a low hum and anything near the background level", () => {
    const hum = audioFeatures(spectrum([50, 100]), sine(0.2), SAMPLE_RATE);
    assert.equal(isSpeechFrame(hum, 0.01), false);
    const quietVoice = audioFeatures(spectrum([300, 600, 900]), sine(0.02), SAMPLE_RATE);
    assert.equal(isSpeechFrame(quietVoice, 0.01), false); // below 3x a 0.01 floor
  });

  it("adapts the noise floor quickly down and slowly up", () => {
    const floor = createNoiseFloor(0.05);
    for (let i = 0; i < 30; i++) floor.update(0.004);
    assert.ok(floor.value < 0.01);
    floor.update(0.5); // one loud frame barely moves it
    assert.ok(floor.value < 0.012);
  });
});

describe("speech detector", () => {
  it("confirms sustained speech once per episode", () => {
    const detector = createSpeechDetector({ windowSize: 10, threshold: 0.6, repeatMs: 20000 });
    const reports = [];
    for (let t = 0; t < 30; t++) {
      const r = detector.push(true, t * 100);
      if (r) reports.push([t, r.confidence]);
    }
    assert.deepEqual(reports, [[9, 1]]);
  });

  it("ignores short bursts like coughs or typing", () => {
    const detector = createSpeechDetector({ windowSize: 10, threshold: 0.6 });
    for (let t = 0; t < 100; t++) assert.equal(detector.push(t % 4 === 0, t * 100), null);
  });

  it("reports again after a quiet gap, or after repeatMs of continuous talking", () => {
    const detector = createSpeechDetector({ windowSize: 10, threshold: 0.6, quiet: 0.2, repeatMs: 5000 });
    let reports = 0;
    let t = 0;
    const feed = (value, frames) => {
      for (let i = 0; i < frames; i++, t += 100) if (detector.push(value, t)) reports += 1;
    };
    feed(true, 10); // first report
    feed(false, 10); // quiet: episode over
    feed(true, 10); // second report
    assert.equal(reports, 2);
    feed(true, 50); // 5 s more talking: one repeat
    assert.equal(reports, 3);
  });
});

describe("evidence tracker", () => {
  // Checks every 2 s; confirmed at 3 of the checks in a 10 s window.
  const tracker = () => createEvidenceTracker({ window: 10000, positives: 3, clearRatio: 0.2, cooldownMs: 60000 });
  const run = (t, hits, start = 0) => hits.map((hit, i) => t.push(hit, start + i * 2000));

  it("ignores a single bad frame", () => {
    const results = run(tracker(), [false, true, false, false, false, false, false]);
    assert.ok(results.every((r) => !r.report));
    assert.equal(results[1].state, "suspected");
    assert.equal(results[6].state, "clear"); // 10 s later the stray hit has aged out
  });

  it("confirms a condition seen in most recent checks, even with gaps", () => {
    const results = run(tracker(), [true, false, true, true]);
    assert.deepEqual(
      results.map((r) => r.report),
      [false, false, false, true],
    );
    assert.equal(results[3].state, "confirmed");
  });

  it("reports one incident once, then again only after the cooldown", () => {
    const t = tracker();
    const reports = run(t, Array(40).fill(true)).filter((r) => r.report).length; // 80 s of the same problem
    assert.equal(reports, 2); // at the start, and once more 60 s later
  });

  it("a brief good frame doesn't end the incident; a clear window does", () => {
    const t = tracker();
    run(t, [true, true, true]); // reported at 4 s
    const flicker = run(t, [false, true, true], 6000);
    assert.ok(flicker.every((r) => !r.report && r.state === "confirmed"));
    const clear = run(t, [false, false, false, false, false], 12000);
    assert.equal(clear.at(-1).state, "clear");
    const again = run(t, [true, true, true], 22000);
    assert.equal(again.filter((r) => r.report).length, 1); // a new incident counts
  });

  it("failed checks are not evidence either way", () => {
    const t = tracker();
    const results = run(t, [true, null, true, null, true]); // every other check failed
    assert.equal(results[4].report, true);
    assert.equal(t.push(null, 9000).state, "confirmed");
    const t2 = tracker();
    run(t2, [true, true]);
    assert.equal(t2.push(null, 4000).report, false); // a failure never completes the evidence
  });
});

describe("camera evidence", () => {
  const frame = (people, extra = {}) => ({ people, peopleConfidence: 0.9, phone: false, phoneConfidence: 0, ...extra });
  const play = (evidence, frames) => frames.map((f, i) => evidence.push(f, i * 2000));
  const events = (results) => results.flatMap((r) => r.events);

  it("a student who looks down or leans out for a moment is not reported", () => {
    const results = play(createCameraEvidence(), [
      frame(1),
      frame(0),
      frame(1, { lookingAway: true }),
      frame(0),
      frame(1),
      frame(1),
    ]);
    assert.deepEqual(events(results), []);
    assert.equal(results[1].face, "absent-suspected");
    assert.equal(results[2].face, "away"); // shown, never counted
  });

  it("someone who leaves is reported once as no_face", () => {
    const results = play(createCameraEvidence(), [frame(1), ...Array(15).fill(frame(0))]);
    assert.deepEqual(
      events(results).map((e) => e.detail),
      ["no_face"],
    );
    assert.equal(results.at(-1).face, "absent");
  });

  it("a second person staying in view is reported once", () => {
    const results = play(createCameraEvidence(), [
      frame(1),
      frame(2),
      frame(2),
      frame(1),
      frame(2),
      frame(2),
      frame(2),
    ]);
    assert.deepEqual(
      events(results).map((e) => [e.type, e.detail]),
      [["face", "multiple_faces"]],
    );
  });

  it("phones go from suspected to detected with repeated evidence", () => {
    const phone = frame(1, { phone: true, phoneSuspected: true, phoneConfidence: 0.7 });
    const results = play(createCameraEvidence(), [frame(1, { phoneSuspected: true }), phone, phone, phone]);
    assert.deepEqual(
      results.map((r) => r.phone),
      ["suspected", "suspected", "suspected", "detected"],
    );
    assert.deepEqual(events(results), [{ type: "phone", detail: "phone_detected", confidence: 0.7 }]);
  });

  it("phone checks can be off for a test", () => {
    const phone = frame(1, { phone: true, phoneSuspected: true });
    const results = play(createCameraEvidence(undefined, { phone: false }), Array(6).fill(phone));
    assert.deepEqual(events(results), []);
    assert.equal(results.at(-1).phone, "none");
  });

  it("uses the server's settings", () => {
    const strict = { absence: { window: 4000, positives: 2 } };
    const results = play(createCameraEvidence(strict), [frame(0), frame(0)]);
    assert.equal(events(results).length, 1);
    assert.equal(detectionConfig(strict).phone.positives, 3); // missing values keep the defaults
  });
});

describe("screen switches", () => {
  it("counts a full-screen exit and the tab hiding with it as one switch", () => {
    const gate = createSwitchGate(3000);
    assert.equal(gate.shouldReport(1000), true);
    assert.equal(gate.shouldReport(1200), false);
    assert.equal(gate.shouldReport(4500), true);
  });

  it("counts a new exit after the student returned to full screen", () => {
    const gate = createSwitchGate(3000);
    assert.equal(gate.shouldReport(1000), true);
    gate.reset(); // back in full screen
    assert.equal(gate.shouldReport(1800), true);
  });
});

describe("warning text", () => {
  it("explains the count and what happens next", () => {
    const w = describeViolation({ type: "screen_switch", detail: "fullscreen_exit", count: 2, limit: 3 });
    assert.equal(w.message, "You left full-screen mode.");
    assert.equal(w.progress, "This is violation 2 of 3.");
    assert.equal(w.consequence, "One more will automatically submit your test.");
  });

  it("shows face deductions and the running adjustment", () => {
    const w = describeViolation({ type: "face", detail: "no_face", count: 2, limit: 5, penalty: 5, totalPenalty: 10 });
    assert.equal(w.deduction, "5 marks deducted. Current score adjustment: −10 marks.");
    assert.equal(w.consequence, "3 more will automatically submit your test.");
  });

  it("handles warn-only limits", () => {
    const w = describeViolation({ type: "voice", detail: "sustained_speech", count: 4, limit: 0 });
    assert.equal(w.progress, "Violations so far: 4.");
    assert.equal(w.consequence, null);
  });

  it("makes unique event ids", () => {
    const ids = new Set(Array.from({ length: 200 }, newEventId));
    assert.equal(ids.size, 200);
    for (const id of ids) assert.match(id, /^[A-Za-z0-9_-]{8,64}$/);
  });
});

describe("proctoring panel", () => {
  const all = { cameraRequired: true, phoneDetection: true, microphoneRequired: true, fullscreenRequired: true };
  const rows = (extra) =>
    Object.fromEntries(
      proctorStatuses({ monitoring: all, cameraLive: true, micLive: true, fullscreen: true, ...extra }).map((r) => [
        r.key,
        [r.state, r.text],
      ]),
    );

  it("shows checking until the first camera check arrives", () => {
    const r = rows({ lastCheck: null });
    assert.deepEqual(r.people, ["checking", "Checking"]);
    assert.deepEqual(r.phone, ["checking", "Checking"]);
    assert.deepEqual(r.microphone, ["ok", "Listening"]);
    assert.deepEqual(r.fullscreen, ["ok", "On"]);
  });

  it("flags people, phones, devices and full screen", () => {
    const check = (face, phone = "none") => rows({ lastCheck: { face, phone } });
    assert.deepEqual(check("ok").people, ["ok", "Just you"]);
    assert.deepEqual(check("away").people, ["notice", "Looking away"]);
    assert.deepEqual(check("absent-suspected").people, ["notice", "Checking: no one visible"]);
    assert.deepEqual(check("absent").people, ["warn", "No one visible"]);
    assert.deepEqual(check("multiple").people, ["warn", "More than one person"]);
    assert.deepEqual(check("ok").phone, ["ok", "No phone detected"]);
    assert.deepEqual(check("ok", "suspected").phone, ["notice", "Phone suspected"]);
    assert.deepEqual(check("ok", "detected").phone, ["warn", "Phone detected"]);
    assert.deepEqual(rows({ lastCheck: { face: "ok" }, cameraLive: false }).people, ["warn", "Camera off"]);
    assert.deepEqual(rows({ micLive: false }).microphone, ["warn", "Disconnected"]);
    assert.deepEqual(rows({ fullscreen: false }).fullscreen, ["warn", "Off"]);
  });

  it("only lists the checks the test runs", () => {
    const keys = proctorStatuses({
      monitoring: { microphoneRequired: true, fullscreenRequired: true },
      micLive: true,
      fullscreen: true,
    }).map((r) => r.key);
    assert.deepEqual(keys, ["microphone", "fullscreen"]);
  });
});

describe("proctoring rules form", () => {
  it("always saves as proctored, even for a test created before proctoring", () => {
    const legacy = {
      enabled: false,
      fullscreenRequired: true,
      cameraRequired: true,
      microphoneRequired: false,
      phoneDetection: true,
      limits: { screen_switch: 3, voice: 5, face: 5, phone: 3 },
      facePenalty: 5,
    };
    const values = monitoringFormValues(legacy);
    assert.equal(values.enabled, true);
    assert.equal(values.microphoneRequired, false);
    assert.equal(values.maxScreenSwitches, 3);
  });
});
