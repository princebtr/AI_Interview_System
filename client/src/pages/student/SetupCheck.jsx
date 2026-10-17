import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircleIcon, ExclamationTriangleIcon } from "@heroicons/react/20/solid";
import api from "../../utils/axios";
import { Button, Card, CardHeader, PageHeader } from "../../components/ui";
import { DeviceCheck } from "../../components/proctoring";
import { buttonStyles } from "../../components/styles";
import {
  createFrameGrabber,
  enterFullscreen,
  exitFullscreen,
  fullscreenSupported,
  mediaErrorMessage,
  requestMedia,
  stopStream,
} from "../../hooks/useProctoring";
import { apiError } from "../../utils/helpers";

const ALL_CHECKS = { cameraRequired: true, microphoneRequired: true, fullscreenRequired: true };
const MULTIPART = { headers: { "Content-Type": "multipart/form-data" } };

/** What one camera check means for the student, in plain words. */
const cameraAdvice = (r) => {
  if (r.people === 0)
    return [false, "We couldn't see you. Face the camera, and add light in front of you rather than behind."];
  if (r.people > 1) return [false, "More than one person is in view. During a test, only you should be visible."];
  if (r.phone || r.phoneSuspected) return [false, "A phone may be in view. Keep phones out of sight during tests."];
  if (r.lookingAway) return [false, "We can see you, but not your face clearly. Face the camera straight on."];
  return [true, "We can see you clearly. Your camera is ready."];
};

const Result = ({ ok, children }) => (
  <p
    role="status"
    className={`flex gap-2 rounded-lg px-3 py-2.5 text-[13px] leading-relaxed ring-1 ${
      ok ? "bg-emerald-50 text-emerald-800 ring-emerald-200" : "bg-amber-50 text-amber-900 ring-amber-200"
    }`}
  >
    {ok ? (
      <CheckCircleIcon className="mt-px size-4 shrink-0 text-emerald-600" />
    ) : (
      <ExclamationTriangleIcon className="mt-px size-4 shrink-0 text-amber-600" />
    )}
    {children}
  </p>
);


/** Try the camera, microphone and full screen before test day. Nothing is recorded. */
const SetupCheck = () => {
  const [stream, setStream] = useState(null);
  const [media, setMedia] = useState({ requesting: false, error: null });
  const [camera, setCamera] = useState({ checking: false, result: null });
  const [fullscreen, setFullscreen] = useState(null); // null | true | error text
  const streamRef = useRef(null);

  useEffect(() => () => stopStream(streamRef.current), []);

  const allow = async () => {
    setMedia({ requesting: true, error: null });
    try {
      const next = await requestMedia({ camera: true, microphone: true });
      streamRef.current = next;
      setStream(next);
      setMedia({ requesting: false, error: null });
    } catch (error) {
      setMedia({ requesting: false, error: mediaErrorMessage(error) });
    }
  };

  const checkCamera = async () => {
    setCamera({ checking: true, result: null });
    const grabber = createFrameGrabber(stream);
    try {
      let blob = null;
      for (let i = 0; i < 10 && !blob; i++) {
        blob = await grabber.grab();
        if (!blob) await new Promise((resolve) => setTimeout(resolve, 200));
      }
      if (!blob) throw new Error("The camera isn't sending a picture yet. Try again in a moment.");
      const form = new FormData();
      form.append("image", blob, "frame.jpg");
      const { data } = await api.post("/ai/analyse-frame", form, MULTIPART);
      setCamera({ checking: false, result: cameraAdvice(data) });
    } catch (error) {
      const message =
        error.response?.status === 503
          ? "Camera checks aren't available on the server right now. Your camera itself works if you can see yourself above."
          : apiError(error, error.message || "Couldn't check the camera. Try again.");
      setCamera({ checking: false, result: [false, message] });
    } finally {
      grabber.stop();
    }
  };

  const tryFullscreen = async () => {
    try {
      await enterFullscreen();
      setFullscreen(true);
      setTimeout(exitFullscreen, 1500);
    } catch (error) {
      setFullscreen(error.message || "Full screen was blocked");
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="My tests"
        title="Check my setup"
        description="Tests are proctored. Try your camera, microphone and full screen here before test day, so nothing gets in the way when a test opens. Nothing is recorded."
        actions={
          <Link to="/tests" className={buttonStyles({ variant: "secondary" })}>
            Back to my tests
          </Link>
        }
      />

      <Card>
        <CardHeader title="Camera and microphone" description="Speak normally: the bar should move." />
        <div className="p-5">
          <DeviceCheck
            monitoring={ALL_CHECKS}
            stream={stream}
            requesting={media.requesting}
            error={media.error}
            onRequest={allow}
          />
        </div>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader
            title="What the proctoring sees"
            description="Runs the same check as during a test on one picture from your camera."
          />
          <div className="space-y-4 p-5">
            {camera.result && <Result ok={camera.result[0]}>{camera.result[1]}</Result>}
            <Button variant="secondary" onClick={checkCamera} loading={camera.checking} disabled={!stream?.getVideoTracks().length}>
              {camera.result ? "Check again" : "Run a camera check"}
            </Button>
            {!stream && <p className="text-[12px] text-slate-500">Allow the camera first.</p>}
          </div>
        </Card>

        <Card>
          <CardHeader title="Full screen" description="Tests run in full screen. This opens it for a moment, then closes it." />
          <div className="space-y-4 p-5">
            {fullscreen === true && <Result ok>Full screen works in this browser.</Result>}
            {typeof fullscreen === "string" && <Result ok={false}>{fullscreen}</Result>}
            {fullscreenSupported() ? (
              <Button variant="secondary" onClick={tryFullscreen}>
                Try full screen
              </Button>
            ) : (
              <Result ok={false}>
                This browser can't go full screen. Use a recent Chrome, Edge, Firefox or Safari on a computer.
              </Result>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
};

export default SetupCheck;
