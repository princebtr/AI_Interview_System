import { useEffect, useLayoutEffect, useRef, useState } from "react";
import api from "../utils/axios";
import { createFrameGrabber, isFullscreen } from "./useProctoring";
import { createCameraEvidence, createSwitchGate, detectionConfig } from "../utils/proctoring";

const MULTIPART = { headers: { "Content-Type": "multipart/form-data" } };

/**
 * Proctoring for AI interview practice: camera checks (people, faces, phones)
 * every couple of seconds with the same evidence rules as tests, full-screen
 * exits and tab switches. Interviews are practice, so
 * nothing is reported to the server as a violation: `onIssue(kind, count)` lets
 * the page warn the student. (Answers are spoken, so there is no speech check.)
 */
export const useInterviewProctoring = ({ active, stream, onIssue }) => {
  const [lastCheck, setLastCheck] = useState(null);
  const [fullscreen, setFullscreen] = useState(() => isFullscreen());
  const [counts, setCounts] = useState({
    screen_switch: 0,
    face: 0,
    phone: 0,
    tabs: 0,
  });
  const issue = useRef(onIssue);
  useLayoutEffect(() => {
    issue.current = onIssue;
  });
  const stopped = useRef(false);

  const countsRef = useRef(counts);
  const bump = (kind) => {
    countsRef.current = {
      ...countsRef.current,
      [kind]: countsRef.current[kind] + 1,
    };
    setCounts(countsRef.current);
    issue.current?.(kind, countsRef.current[kind]);
  };

  // A new session starts from zero.
  useEffect(() => {
    if (!active) return;
    stopped.current = false;
    countsRef.current = { screen_switch: 0, face: 0, phone: 0, tabs: 0 };
    setCounts(countsRef.current);
    setLastCheck(null);
  }, [active]);

  // The server's detection timings (the defaults until they arrive).
  const [detection, setDetection] = useState(null);
  useEffect(() => {
    if (!active) return;
    api
      .get("/ai/proctoring-config")
      .then(({ data }) => setDetection(data.detection))
      .catch(() => {});
  }, [active]);
  const frameEveryMs = detectionConfig(detection).frameIntervalMs;

  // People and phones: each confirmed incident counts once (see createCameraEvidence).
  useEffect(() => {
    if (!active || !stream?.getVideoTracks().length) return undefined;
    const grabber = createFrameGrabber(stream);
    const evidence = createCameraEvidence(detection);
    let busy = false;
    const check = async () => {
      if (busy) return;
      busy = true;
      try {
        const blob = await grabber.grab();
        if (!blob) return;
        const form = new FormData();
        form.append("image", blob, "frame.jpg");
        const { data } = await api.post("/ai/analyse-frame", form, MULTIPART);
        if (stopped.current) return;
        const now = Date.now();
        const { face, phone, events } = evidence.push(data, now);
        setLastCheck({ ...data, face, phone, at: now });
        events.forEach((event) => bump(event.type));
      } catch {
        evidence.push(null, Date.now()); // a missed check doesn't count against the student
      } finally {
        busy = false;
      }
    };
    const timer = setInterval(check, frameEveryMs);
    const first = setTimeout(check, 500);
    return () => {
      clearInterval(timer);
      clearTimeout(first);
      grabber.stop();
    };
     
  }, [active, stream, detection, frameEveryMs]);

  // Full-screen exits and tab switches (one action that does both counts once).
  useEffect(() => {
    if (!active) return undefined;
    const gate = createSwitchGate(3000);
    const onChange = () => {
      const now = isFullscreen();
      setFullscreen(now);
      if (now) gate.reset();
      else if (!stopped.current && gate.shouldReport(Date.now())) bump("screen_switch");
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden" && !stopped.current) bump("tabs");
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
  }, [active]);

  // Ends the session's checks at once (before React re-renders), so leaving full
  // screen on purpose isn't counted.
  const stop = () => {
    stopped.current = true;
  };

  return { lastCheck, fullscreen, counts, stop };
};
