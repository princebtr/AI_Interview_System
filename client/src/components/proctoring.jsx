// UI for monitored tests: the rules, the device check, in-test status and warnings,
// and the educator's settings and per-student report.
import { useEffect, useRef, useState } from "react";
import {
  ArrowsPointingOutIcon,
  CheckCircleIcon,
  DevicePhoneMobileIcon,
  ExclamationTriangleIcon,
  MicrophoneIcon,
  ShieldCheckIcon,
  ShieldExclamationIcon,
  VideoCameraIcon,
  XCircleIcon,
} from "@heroicons/react/24/outline";
import { XMarkIcon } from "@heroicons/react/20/solid";
import { Badge, Button, Card, CardHeader, LiveDot, Spinner } from "./ui";
import { fullscreenSupported } from "../hooks/useProctoring";
import { cx } from "../utils/helpers";
import {
  DETAIL_LABELS,
  LIMIT_REASONS,
  REASON_TEXT,
  VIOLATION_LABELS,
  VIOLATION_TYPES,
  activeChecks,
  proctorStatuses,
  reasonLabel,
} from "../utils/proctoring";
import { formatClockTime } from "../utils/time";

const ICONS = {
  screen_switch: ArrowsPointingOutIcon,
  voice: MicrophoneIcon,
  face: VideoCameraIcon,
  phone: DevicePhoneMobileIcon,
  technical: ExclamationTriangleIcon,
};

const limitText = (limit) =>
  limit > 0
    ? `${limit} ${limit === 1 ? "time submits" : "times submit"} your test automatically.`
    : "You'll be warned, but it won't submit your test.";

/* ---------------------------------------------------------------------------- */
/* Before the test                                                              */
/* ---------------------------------------------------------------------------- */

/** The rules a student agrees to before starting. */
export const MonitoringRules = ({ monitoring, practice = false }) => {
  const { limits = {}, facePenalty = 0 } = monitoring;
  const rules = [
    monitoring.fullscreenRequired && {
      icon: ArrowsPointingOutIcon,
      title: "Stay in full screen",
      text: `Leaving full screen, switching tabs or apps, or reloading the page counts as a screen switch. ${limitText(limits.screen_switch)}`,
    },
    monitoring.cameraRequired && {
      icon: VideoCameraIcon,
      title: "Keep your camera on, with only you in view",
      text: `Checked every few seconds. If no one, or more than one person, is visible for about 15 seconds, it counts${facePenalty ? ` and costs ${facePenalty} mark${facePenalty === 1 ? "" : "s"}` : ""}. ${limitText(limits.face)}`,
    },
    monitoring.microphoneRequired && {
      icon: MicrophoneIcon,
      title: "No talking",
      text: `Sustained speech counts; short sounds and typing don't. ${limitText(limits.voice)}`,
    },
    monitoring.phoneDetection && {
      icon: DevicePhoneMobileIcon,
      title: "No phones",
      text: `A phone the camera can see counts. ${limitText(limits.phone)}`,
    },
  ].filter(Boolean);

  return (
    <div className="space-y-3">
      <ul className="space-y-3">
        {rules.map(({ icon: Icon, title, text }) => (
          <li key={title} className="flex gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-50 text-accent-700 ring-1 ring-accent-100">
              {Icon && <Icon className="size-[18px]" />}
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-900">{title}</p>
              <p className="mt-0.5 text-[13px] leading-relaxed text-slate-600">{text}</p>
            </div>
          </li>
        ))}
      </ul>
      <p className="flex gap-2 rounded-lg bg-slate-50 px-3 py-2.5 text-[12px] leading-relaxed text-slate-600 ring-1 ring-slate-200/70">
        <ShieldCheckIcon className="size-4 shrink-0 text-emerald-600" />
        <span>
          Nothing is recorded. Camera frames are checked by Cohortix and discarded; audio is analysed only in your
          browser. The checks never identify you, and they can be wrong
          {practice
            ? ". In practice tests they only warn you and count towards the limits."
            : ": your educator can review any flag and reverse it."}
        </span>
      </p>
    </div>
  );
};

/** Live input level for the microphone check. */
const MicMeter = ({ stream }) => {
  const [level, setLevel] = useState(0);
  useEffect(() => {
    const track = stream?.getAudioTracks()[0];
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!track || !Context) return undefined;
    const context = new Context();
    const source = context.createMediaStreamSource(new MediaStream([track]));
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const data = new Float32Array(analyser.fftSize);
    context.resume?.().catch(() => {});
    const timer = setInterval(() => {
      analyser.getFloatTimeDomainData(data);
      const rms = Math.sqrt(data.reduce((sum, x) => sum + x * x, 0) / data.length);
      setLevel(Math.min(1, rms * 8));
    }, 120);
    return () => {
      clearInterval(timer);
      source.disconnect();
      context.close().catch(() => {});
    };
  }, [stream]);
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200"
      role="meter"
      aria-label="Microphone level"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(level * 100)}
    >
      <div
        className="bg-primary h-full rounded-full transition-[width] duration-100"
        style={{ width: `${level * 100}%` }}
      />
    </div>
  );
};

/** Shows a MediaStream in a muted <video>. */
export const StreamVideo = ({ stream, videoRef, className }) => {
  const own = useRef(null);
  const ref = videoRef ?? own;
  useEffect(() => {
    if (ref.current && ref.current.srcObject !== stream) ref.current.srcObject = stream ?? null;
  }, [stream, ref]);
  return <video ref={ref} autoPlay playsInline muted className={className} aria-label="Your camera" />;
};

const CheckRow = ({ ok, pending, label, children }) => (
  <li className="flex items-start gap-2.5">
    {pending ? (
      <span className="mt-0.5 size-5 shrink-0 rounded-full border-2 border-slate-200" />
    ) : ok ? (
      <CheckCircleIcon className="size-5 shrink-0 text-emerald-600" />
    ) : (
      <XCircleIcon className="size-5 shrink-0 text-red-500" />
    )}
    <div className="min-w-0 flex-1">
      <p className="text-sm font-medium text-slate-800">{label}</p>
      {children}
    </div>
  </li>
);

/** Camera, microphone and full-screen readiness, before starting or resuming. */
export const DeviceCheck = ({ monitoring, stream, requesting, error, onRequest }) => {
  const needsMedia = monitoring.cameraRequired || monitoring.microphoneRequired;
  const hasVideo = Boolean(stream?.getVideoTracks().length);
  const hasAudio = Boolean(stream?.getAudioTracks().length);
  const ready = Boolean(stream);
  return (
    <div className="grid gap-5 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      {monitoring.cameraRequired && (
        <div className="relative aspect-[4/3] overflow-hidden rounded-lg bg-slate-900">
          {hasVideo ? (
            <StreamVideo stream={stream} className="size-full -scale-x-100 object-cover" />
          ) : (
            <div className="flex size-full flex-col items-center justify-center gap-2 text-slate-400">
              <VideoCameraIcon className="size-8" />
              <span className="text-[13px]">Camera preview</span>
            </div>
          )}
        </div>
      )}
      <div className="space-y-4">
        <ul className="space-y-3">
          {monitoring.cameraRequired && (
            <CheckRow ok={hasVideo} pending={!ready && !error} label="Camera">
              <p className="text-[12px] text-slate-500">Sit facing it, in good light, alone.</p>
            </CheckRow>
          )}
          {monitoring.microphoneRequired && (
            <CheckRow ok={hasAudio} pending={!ready && !error} label="Microphone">
              {hasAudio ? (
                <div className="mt-1.5">
                  <MicMeter stream={stream} />
                </div>
              ) : (
                <p className="text-[12px] text-slate-500">Used only to notice talking.</p>
              )}
            </CheckRow>
          )}
          {monitoring.fullscreenRequired && (
            <CheckRow ok={fullscreenSupported()} label="Full screen">
              <p className="text-[12px] text-slate-500">
                {fullscreenSupported()
                  ? "Starts when you begin the test."
                  : "This browser can't go full screen. Use a recent Chrome, Edge, Firefox or Safari."}
              </p>
            </CheckRow>
          )}
        </ul>
        {error && (
          <p
            role="alert"
            className="rounded-lg bg-red-50 px-3 py-2.5 text-[13px] leading-relaxed text-red-800 ring-1 ring-red-200"
          >
            {error}
          </p>
        )}
        {needsMedia && !ready && (
          <Button variant="secondary" onClick={onRequest} loading={requesting}>
            {error ? "Try again" : "Allow camera and microphone"}
          </Button>
        )}
      </div>
    </div>
  );
};

/* ---------------------------------------------------------------------------- */
/* During the test                                                              */
/* ---------------------------------------------------------------------------- */

const countTone = (count, limit) =>
  !count
    ? "text-slate-500 ring-slate-200 bg-white"
    : limit > 0 && count >= limit - 1
      ? "text-red-700 ring-red-200 bg-red-50"
      : "text-amber-800 ring-amber-200 bg-amber-50";

/** Camera thumbnail and per-check counts in the test's top bar. */
export const MonitorBar = ({ monitoring, stream, videoRef, cameraLive, micLive }) => {
  const counts = monitoring.counts ?? {};
  return (
    <div className="flex items-center gap-2">
      {monitoring.cameraRequired && (
        // Always rendered: the camera checks read their frames from this video.
        <div className="relative shrink-0">
          <StreamVideo
            stream={stream}
            videoRef={videoRef}
            className="h-9 w-12 -scale-x-100 rounded-md bg-slate-900 object-cover"
          />
          <span
            className={cx(
              "absolute -top-1 -right-1 size-2.5 rounded-full ring-2 ring-white",
              cameraLive ? "bg-emerald-500" : "bg-red-500",
            )}
          />
        </div>
      )}
      <ul className="flex flex-wrap items-center gap-1" aria-label="Proctoring">
        {activeChecks(monitoring).map((type) => {
          const Icon = ICONS[type];
          const limit = monitoring.limits?.[type] ?? 0;
          const count = counts[type] ?? 0;
          const off = type === "face" || type === "phone" ? !cameraLive : type === "voice" ? !micLive : false;
          return (
            <li
              key={type}
              title={`${VIOLATION_LABELS[type]}: ${count}${limit ? ` of ${limit}` : ""}${off ? " (device disconnected)" : ""}`}
              className={cx(
                "flex items-center gap-1 rounded-md px-1.5 py-1 text-[12px] font-semibold tabular-nums ring-1",
                off ? "bg-red-50 text-red-700 ring-red-200" : countTone(count, limit),
              )}
            >
              {Icon && <Icon className="size-3.5" aria-hidden="true" />}
              <span className="sr-only">{VIOLATION_LABELS[type]}</span>
              {count}
              {limit > 0 && <span className="font-normal opacity-60">/{limit}</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
};

const STATUS_ICON = {
  ok: <CheckCircleIcon className="size-4 text-emerald-600" />,
  notice: <ExclamationTriangleIcon className="size-4 text-amber-500" />,
  warn: <ExclamationTriangleIcon className="size-4 text-amber-600" />,
  checking: <Spinner className="size-4 text-slate-400" />,
};

/** The live proctoring panel shown during every proctored test (like the AI interview's). */
export const ProctoringPanel = ({ monitoring, stream, lastCheck, cameraLive, micLive, fullscreen }) => {
  const rows = proctorStatuses({ monitoring, lastCheck, cameraLive, micLive, fullscreen });
  const counts = monitoring.counts ?? {};
  return (
    <Card>
      <CardHeader
        title="Proctoring"
        description="Checks run every few seconds. Nothing is recorded."
        action={
          <Badge tone="danger">
            <LiveDot />
            Live
          </Badge>
        }
      />
      <div className={cx("grid gap-4 p-4", monitoring.cameraRequired && "sm:grid-cols-[220px_minmax(0,1fr)]")}>
        {monitoring.cameraRequired && (
          <div className="relative aspect-[4/3] overflow-hidden rounded-lg bg-slate-900">
            <StreamVideo stream={stream} className="size-full -scale-x-100 object-cover" />
          </div>
        )}
        <div className="min-w-0 space-y-3">
          <dl className="divide-y divide-slate-100 rounded-lg ring-1 ring-slate-200/70">
            {rows.map((row) => (
              <div key={row.key} className="flex items-center justify-between gap-3 px-3 py-2">
                <dt className="text-[13px] text-slate-500">{row.label}</dt>
                <dd
                  className={cx(
                    "flex items-center gap-1.5 text-[13px] font-medium",
                    row.state === "warn" ? "text-amber-800" : "text-slate-800",
                  )}
                >
                  {row.text}
                  {STATUS_ICON[row.state]}
                </dd>
              </div>
            ))}
          </dl>
          <p className="text-[12px] leading-relaxed text-slate-500">
            {activeChecks(monitoring)
              .map((type) => {
                const limit = monitoring.limits?.[type] ?? 0;
                return `${VIOLATION_LABELS[type]} ${counts[type] ?? 0}${limit ? `/${limit}` : ""}`;
              })
              .join(" · ")}
          </p>
        </div>
      </div>
    </Card>
  );
};

/** Non-blocking warnings after confirmed violations (announced to screen readers). */
export const WarningStack = ({ warnings, onDismiss }) => (
  <div
    aria-live="assertive"
    className="fixed right-4 bottom-4 z-[60] flex w-[min(26rem,calc(100vw-2rem))] flex-col gap-2"
  >
    {warnings.map((w) => {
      const Icon = ICONS[w.type] ?? ExclamationTriangleIcon;
      const severe = w.severe;
      return (
        <div
          key={w.id}
          role="alert"
          className={cx(
            "fade-in flex gap-3 rounded-lg border bg-white p-4 shadow-lift",
            severe ? "border-red-200" : "border-amber-200",
          )}
        >
          <span
            className={cx(
              "flex size-9 shrink-0 items-center justify-center rounded-lg",
              severe ? "bg-red-50 text-red-600" : "bg-amber-50 text-amber-700",
            )}
          >
            {Icon && <Icon className="size-5" />}
          </span>
          <div className="min-w-0 flex-1 text-[13px] leading-relaxed">
            <p className="text-sm font-semibold text-slate-900">{w.title}</p>
            <p className="text-slate-700">
              {w.message} {w.progress}
            </p>
            {w.deduction && <p className="mt-0.5 font-medium text-red-700">{w.deduction}</p>}
            {w.consequence && (
              <p className={cx("mt-0.5", severe ? "font-medium text-red-700" : "text-slate-500")}>{w.consequence}</p>
            )}
          </div>
          <button
            type="button"
            onClick={() => onDismiss(w.id)}
            aria-label="Dismiss warning"
            className="-m-1 self-start rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            <XMarkIcon className="size-4" />
          </button>
        </div>
      );
    })}
  </div>
);

/** Blocks the test until the student returns to full screen. */
export const FullscreenLost = ({ count, limit, error, onReturn }) => (
  <div
    className="fixed inset-0 z-[55] flex items-center justify-center bg-slate-900/70 p-4 backdrop-blur-sm"
    role="alertdialog"
    aria-modal="true"
    aria-labelledby="fs-lost-title"
    aria-describedby="fs-lost-body"
  >
    <Card className="fade-in w-full max-w-md p-6 text-center">
      <span className="mx-auto flex size-12 items-center justify-center rounded-full bg-amber-50 text-amber-700 ring-1 ring-amber-200">
        <ArrowsPointingOutIcon className="size-6" />
      </span>
      <h2 id="fs-lost-title" className="mt-4 text-lg font-bold text-slate-900">
        You left full screen
      </h2>
      <div id="fs-lost-body" className="mt-2 space-y-1 text-sm leading-relaxed text-slate-600">
        <p>
          {limit > 0 ? `This is screen switch ${count} of ${limit}.` : `Screen switches so far: ${count}.`} Your answers
          are saved and the timer keeps running.
        </p>
        {limit > 0 && limit - count === 1 && (
          <p className="font-medium text-red-700">One more will automatically submit your test.</p>
        )}
      </div>
      {error && (
        <p role="alert" className="mt-3 text-[13px] text-red-700">
          {error}
        </p>
      )}
      <Button className="mt-5 w-full" size="lg" onClick={onReturn} autoFocus>
        <ArrowsPointingOutIcon className="size-4" />
        Return to full screen
      </Button>
    </Card>
  </div>
);

export const SubmittingOverlay = () => (
  <div
    className="fixed inset-0 z-[55] flex items-center justify-center bg-slate-900/70 p-4 backdrop-blur-sm"
    role="status"
  >
    <Card className="flex items-center gap-3 px-6 py-5 text-sm font-medium text-slate-800">
      <Spinner className="size-5 text-accent-600" /> A proctoring limit was reached. Submitting your test…
    </Card>
  </div>
);

/** Why an automatically submitted test ended, on the student's result page. */
export const ReasonBanner = ({ reason, practice = false }) =>
  LIMIT_REASONS.has(reason) ? (
    <div
      role="status"
      className="flex gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm leading-relaxed text-red-900"
    >
      <ShieldExclamationIcon className="size-5 shrink-0" />
      <div>
        <p className="font-semibold">Submitted automatically</p>
        <p>
          {REASON_TEXT[reason]} Your answers up to that moment were graded.{" "}
          {practice
            ? "Practice tests follow the same proctoring rules as real tests, so you know what to expect."
            : "If you think a flag was wrong, ask your educator to review it."}
        </p>
      </div>
    </div>
  ) : null;

/** Full-viewport exam layout for proctored tests, above the app's navigation. */
export const ExamFrame = ({ children }) => (
  <div className="fixed inset-0 z-40 overflow-y-auto bg-slate-50">
    <div className="mx-auto w-full max-w-6xl px-4 pb-10 sm:px-6 lg:px-10">{children}</div>
  </div>
);

/* ---------------------------------------------------------------------------- */
/* Educators                                                                    */
/* ---------------------------------------------------------------------------- */

/** Non-zero violation counts as compact badges. */
export const ViolationBadges = ({ counts }) => {
  const shown = VIOLATION_TYPES.filter((type) => counts?.[type]);
  if (!shown.length) return <span className="text-slate-400">—</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {shown.map((type) => (
        <Badge key={type} tone="warning">
          {VIOLATION_LABELS[type]} {counts[type]}
        </Badge>
      ))}
    </span>
  );
};

const ACTION_TEXT = {
  warned: "Warned",
  penalised: "Marks deducted",
  auto_submitted: "Submitted the test",
  logged: "Logged",
  ignored: "After submission",
};

/** One student's proctoring report: scores, counts and a reviewable timeline. */
export const MonitoringReport = ({ result, monitoring, totalMarks, events, onReview, reviewing }) => {
  const submitted = result.status === "submitted";
  return (
    <div className="space-y-6 p-5">
      <dl className="grid grid-cols-3 gap-3 text-center">
        {[
          ["Raw score", result.rawScore ?? "—"],
          ["Penalties", result.totalPenalty ? `−${result.totalPenalty}` : "0"],
          ["Final", result.score ?? "—"],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg bg-slate-50 px-3 py-3 ring-1 ring-slate-200/70">
            <dt className="text-[12px] text-slate-500">{label}</dt>
            <dd className="mt-0.5 text-lg font-bold text-slate-900 tabular-nums">
              {value}
              {label !== "Penalties" && value !== "—" && (
                <span className="text-[12px] font-medium text-slate-400"> / {totalMarks}</span>
              )}
            </dd>
          </div>
        ))}
      </dl>

      <div className="space-y-2 text-[13px]">
        <p className="flex justify-between gap-3">
          <span className="text-slate-500">Submission</span>
          <span className="font-medium text-slate-900">
            {result.submissionReason ? reasonLabel(result.submissionReason) : "Not submitted yet"}
          </span>
        </p>
        <p className="flex justify-between gap-3">
          <span className="text-slate-500">Camera checks run</span>
          <span className="font-medium text-slate-900 tabular-nums">{result.framesAnalysed ?? 0}</span>
        </p>
        {activeChecks(monitoring).map((type) => (
          <p key={type} className="flex justify-between gap-3">
            <span className="text-slate-500">{VIOLATION_LABELS[type]} violations</span>
            <span className="font-medium text-slate-900 tabular-nums">
              {result.violations?.[type] ?? 0}
              {monitoring.limits?.[type] > 0 && <span className="text-slate-400"> of {monitoring.limits[type]}</span>}
            </span>
          </p>
        ))}
      </div>

      <section aria-labelledby="timeline-title">
        <h3 id="timeline-title" className="text-sm font-semibold text-slate-900">
          Timeline
        </h3>
        {!events ? (
          <div className="mt-3 h-20 animate-pulse rounded-lg bg-slate-100" />
        ) : events.length === 0 ? (
          <p className="mt-2 text-[13px] text-slate-500">No events recorded.</p>
        ) : (
          <ol className="mt-3 space-y-2">
            {events.map((e) => {
              const Icon = ICONS[e.type] ?? ExclamationTriangleIcon;
              const dismissed = e.reviewStatus === "dismissed";
              return (
                <li
                  key={e.id}
                  className={cx(
                    "rounded-lg border p-3",
                    dismissed ? "border-slate-200 bg-slate-50" : "border-slate-200/70 bg-white",
                  )}
                >
                  <div className="flex items-start gap-2.5">
                    {Icon && (
                      <Icon
                        className={cx(
                          "mt-0.5 size-4 shrink-0",
                          e.type === "technical" ? "text-slate-400" : "text-amber-600",
                        )}
                      />
                    )}
                    <div className="min-w-0 flex-1">
                      <p
                        className={cx(
                          "text-[13px] font-medium text-slate-900",
                          dismissed && "line-through decoration-slate-400",
                        )}
                      >
                        {DETAIL_LABELS[e.detail] ?? e.detail}
                      </p>
                      <p className="text-[12px] text-slate-500 tabular-nums">
                        {formatClockTime(e.occurredAt)}
                        {e.confidence != null && ` · ${Math.round(e.confidence * 100)}% confidence`}
                        {` · ${ACTION_TEXT[e.actionTaken] ?? e.actionTaken}`}
                        {e.penaltyApplied > 0 && ` (−${e.penaltyApplied})`}
                      </p>
                    </div>
                    {e.type !== "technical" && e.reviewStatus !== "unreviewed" && (
                      <Badge tone={dismissed ? "neutral" : "danger"}>{dismissed ? "Dismissed" : "Upheld"}</Badge>
                    )}
                  </div>
                  {submitted && e.type !== "technical" && e.actionTaken !== "ignored" && (
                    <div className="mt-2 flex gap-2 pl-6">
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={e.reviewStatus === "upheld"}
                        loading={reviewing === `${e.id}:upheld`}
                        onClick={() => onReview(e, "upheld")}
                      >
                        Uphold
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={dismissed}
                        loading={reviewing === `${e.id}:dismissed`}
                        onClick={() => onReview(e, "dismissed")}
                      >
                        Dismiss{e.penaltyApplied > 0 ? ` and refund ${e.penaltyApplied}` : ""}
                      </Button>
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </section>
    </div>
  );
};

const Toggle = ({ id, checked, onChange, disabled, label, description }) => (
  <label
    htmlFor={id}
    className={cx("flex items-start gap-3", disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer")}
  >
    <input
      id={id}
      type="checkbox"
      className="mt-0.5 size-4 rounded border-slate-300"
      checked={checked}
      disabled={disabled}
      onChange={(e) => onChange(e.target.checked)}
    />
    <span>
      <span className="block text-sm font-medium text-slate-800">{label}</span>
      {description && <span className="block text-[13px] leading-relaxed text-slate-500">{description}</span>}
    </span>
  </label>
);

const NumberField = ({ id, label, value, onChange, min, max, suffix, disabled }) => (
  <label htmlFor={id} className="flex items-center justify-between gap-3 text-[13px] text-slate-600">
    {label}
    <span className="flex items-center gap-1.5">
      <input
        id={id}
        type="number"
        min={min}
        max={max}
        value={value}
        disabled={disabled}
        onChange={(e) =>
          onChange(e.target.value === "" ? "" : Math.max(min, Math.min(max, parseInt(e.target.value, 10) || 0)))
        }
        className="h-8 w-16 rounded-md border border-slate-200 bg-white px-2 text-right text-sm text-slate-900 tabular-nums focus:border-accent-500 focus:ring-2 focus:ring-accent-500 focus:ring-offset-1 focus:outline-none disabled:bg-slate-50"
      />
      {suffix && <span className="w-14 text-[12px] text-slate-400">{suffix}</span>}
    </span>
  </label>
);

/** Proctoring rules for the create/edit test forms. `capabilities` from /proctoring/capabilities.
 * Every test is proctored: educators choose the checks and limits, not whether to proctor. */
export const MonitoringSettings = ({ value, onChange, capabilities }) => {
  const set = (key) => (v) => onChange({ ...value, [key]: v });
  const camera = capabilities?.cameraChecks !== false;
  return (
    <div className="space-y-5">
      <p className="flex gap-2 rounded-lg bg-accent-50/60 px-3 py-2.5 text-[13px] leading-relaxed text-slate-600 ring-1 ring-accent-100">
        <ShieldCheckIcon className="size-4 shrink-0 text-accent-600" />
        <span>
          Every test is proctored. Students see these rules and allow their camera and microphone before they start.
          Limits of 0 only warn.
        </span>
      </p>
      <div className="space-y-5">
        <div className="space-y-2.5">
          <Toggle
            id="mon-fullscreen"
            checked={value.fullscreenRequired}
            onChange={set("fullscreenRequired")}
            label="Require full screen"
            description="Leaving full screen, switching tabs or reloading counts as a screen switch."
          />
          <NumberField
            id="mon-max-switch"
            label="Screen switches before submitting"
            value={value.maxScreenSwitches}
            onChange={set("maxScreenSwitches")}
            min={0}
            max={20}
            disabled={!value.fullscreenRequired}
          />
        </div>
        <div className="space-y-2.5">
          <Toggle
            id="mon-camera"
            checked={value.cameraRequired && camera}
            onChange={set("cameraRequired")}
            disabled={!camera}
            label="Camera checks"
            description={
              camera
                ? "Flags when no one, or more than one person, is in view. People are detected, not identified."
                : "Unavailable: the detection model isn't installed on this server."
            }
          />
          <NumberField
            id="mon-max-face"
            label="Camera violations before submitting"
            value={value.maxFaceViolations}
            onChange={set("maxFaceViolations")}
            min={0}
            max={50}
            disabled={!value.cameraRequired || !camera}
          />
          <NumberField
            id="mon-face-penalty"
            label="Marks deducted per camera violation"
            value={value.facePenalty}
            onChange={set("facePenalty")}
            min={0}
            max={100}
            suffix="marks"
            disabled={!value.cameraRequired || !camera}
          />
          <Toggle
            id="mon-phone"
            checked={value.phoneDetection && value.cameraRequired && camera}
            onChange={set("phoneDetection")}
            disabled={!value.cameraRequired || !camera}
            label="Phone detection"
            description="Flags a phone the camera can see clearly. Phones out of view can't be detected."
          />
          <NumberField
            id="mon-max-phone"
            label="Phone detections before submitting"
            value={value.maxPhoneViolations}
            onChange={set("maxPhoneViolations")}
            min={0}
            max={20}
            disabled={!value.cameraRequired || !value.phoneDetection || !camera}
          />
        </div>
        <div className="space-y-2.5">
          <Toggle
            id="mon-mic"
            checked={value.microphoneRequired}
            onChange={set("microphoneRequired")}
            label="Microphone checks"
            description="Flags sustained speech, analysed in the student's browser. It can't tell how many people are talking."
          />
          <NumberField
            id="mon-max-voice"
            label="Speech detections before submitting"
            value={value.maxVoiceViolations}
            onChange={set("maxVoiceViolations")}
            min={0}
            max={50}
            disabled={!value.microphoneRequired}
          />
        </div>
      </div>
    </div>
  );
};

/** One-line summary of a test's rules for headers and lists. */
export const MonitoringSummary = ({ monitoring }) => {
  if (!monitoring?.enabled)
    return <span className="text-slate-500">Not proctored: created before proctoring was added</span>;
  const parts = activeChecks(monitoring).map((type) => {
    const limit = monitoring.limits?.[type];
    return `${VIOLATION_LABELS[type]} ${limit ? `(${limit} max)` : "(warn only)"}`;
  });
  return (
    <span className="text-slate-600">
      {parts.join(" · ")}
      {monitoring.cameraRequired &&
        monitoring.facePenalty > 0 &&
        ` · −${monitoring.facePenalty} marks per camera violation`}
    </span>
  );
};
