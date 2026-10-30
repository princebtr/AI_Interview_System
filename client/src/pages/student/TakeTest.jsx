import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useParams } from "react-router-dom";
import toast from "react-hot-toast";
import { ArrowRightIcon, CheckCircleIcon, ChevronRightIcon, ClockIcon, XCircleIcon } from "@heroicons/react/20/solid";
import api from "../../utils/axios";
import { useServerClock } from "../../hooks/useServerClock";
import {
  enterFullscreen,
  exitFullscreen,
  fullscreenSupported,
  mediaErrorMessage,
  requestMedia,
  stopStream,
  takePendingLeave,
  useProctoring,
} from "../../hooks/useProctoring";
import {
  DeviceCheck,
  FullscreenLost,
  MonitoringRules,
  ReasonBanner,
  SubmittingOverlay,
  WarningStack,
} from "../../components/proctoring";
import { checkChips, describeViolation, newEventId, proctorStatuses } from "../../utils/proctoring";
import {
  ExamShell,
  NextButton,
  OptionList,
  ProctorSidebar,
  QuestionFooter,
  QuestionHeader,
  QuestionList,
  QuestionTags,
  ReviewToggle,
} from "../../components/exam";
import { Button, Card, CardHeader, Kbd, PageHeader, Spinner } from "../../components/ui";
import { LoadError, LoadingBlock } from "../../components/data";
import { ClipboardDocumentListIcon } from "@heroicons/react/24/outline";
import { TestStatusBadge } from "../../components/tests";
import { apiError, cx } from "../../utils/helpers";
import { countdown, formatClockTime, formatDateTime, formatDuration } from "../../utils/time";

const LETTERS = ["A", "B", "C", "D"];
const NUMBER_KEYS = { 1: "A", 2: "B", 3: "C", 4: "D" };
const EMPTY_SHEET = { answers: {}, review: [] };
const NO_QUESTIONS = [];
// Spoken reminders for screen-reader users, in minutes left.
const ANNOUNCE_AT = [30, 15, 10, 5, 1];

const Breadcrumb = ({ title }) => (
  <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-[13px] text-slate-500">
    <Link to="/tests" className="hover:text-slate-800">
      My tests
    </Link>
    <ChevronRightIcon className="size-4 text-slate-300" />
    <span className="truncate font-medium text-slate-800">{title}</span>
  </nav>
);

const SaveState = ({ state }) => {
  if (state === "saving") {
    return (
      <span className="flex items-center gap-1.5 text-[12px] text-slate-500">
        <Spinner className="size-3" /> Saving
      </span>
    );
  }
  if (state === "error") return <span className="text-[12px] font-medium text-red-600">Not saved, retrying…</span>;
  return (
    <span className="flex items-center gap-1 text-[12px] text-slate-500">
      <CheckCircleIcon className="size-3.5 text-emerald-600" /> Saved
    </span>
  );
};

const Timer = ({ ms }) => (
  <span
    role="timer"
    aria-label={`Time left ${countdown(ms)}`}
    className={cx(
      "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 font-mono text-sm font-semibold tabular-nums",
      ms < 60_000
        ? "bg-red-600 text-white"
        : ms < 5 * 60_000
          ? "bg-amber-100 text-amber-900"
          : "bg-white text-slate-900 ring-1 ring-slate-200",
    )}
  >
    <ClockIcon className="size-4" />
    {countdown(ms)}
  </span>
);

/** Modal confirmation; the page behind it is inert while it's open. */
const ConfirmSubmit = ({ answered, total, flagged, submitting, onCancel, onConfirm }) => {
  const cancelButton = useRef(null);
  const cancel = useRef(onCancel);
  useLayoutEffect(() => {
    cancel.current = onCancel;
  }, [onCancel]);

  useEffect(() => {
    const previouslyFocused = document.activeElement;
    const app = document.getElementById("root");
    app?.setAttribute("inert", "");
    cancelButton.current?.focus();
    const onKey = (e) => e.key === "Escape" && cancel.current();
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      app?.removeAttribute("inert");
      previouslyFocused?.focus?.();
    };
  }, []);

  const unanswered = total - answered;
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="submit-title"
      aria-describedby="submit-body"
    >
      <div className="fade-in absolute inset-0 bg-slate-900/40" onClick={() => cancel.current()} />
      <div className="fade-in relative w-full max-w-sm rounded-lg border border-slate-200 bg-white p-6 shadow-xl">
        <h2 id="submit-title" className="text-base font-semibold text-slate-900">
          Submit your test?
        </h2>
        <div id="submit-body" className="mt-2 space-y-2 text-sm leading-relaxed text-slate-600">
          <p>
            You've answered{" "}
            <span className="font-medium text-slate-900">
              {answered} of {total}
            </span>{" "}
            questions.
            {unanswered > 0 && ` ${unanswered} unanswered question${unanswered === 1 ? "" : "s"} will score zero.`}
            {flagged > 0 && ` ${flagged} ${flagged === 1 ? "is" : "are"} still marked for review.`}
          </p>
          <p>You can't change your answers after submitting.</p>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button ref={cancelButton} variant="secondary" onClick={() => cancel.current()}>
            Keep working
          </Button>
          <Button onClick={onConfirm} loading={submitting}>
            Submit
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
};

const Result = ({ test, attempt }) => (
  <div className="space-y-6">
    <ReasonBanner reason={attempt.submissionReason} />
    <Card>
      <div className="flex flex-col gap-6 p-6 sm:flex-row sm:items-center">
        <div className="flex size-24 shrink-0 items-center justify-center rounded-full bg-accent-50 ring-8 ring-accent-100/60">
          <span className="text-accent-600 text-2xl font-bold tabular-nums">{Math.round(attempt.percentage)}%</span>
        </div>
        <div>
          <p className="text-[13px] font-medium text-slate-500">Your score</p>
          <p className="mt-1 text-2xl font-semibold tracking-tight text-slate-900 tabular-nums">
            {attempt.score} / {test.totalMarks} marks
          </p>
          <p className="mt-1 text-sm text-slate-500">
            {attempt.correct} of {test.questionCount} correct ·{" "}
            {attempt.submissionReason === "TIME_LIMIT"
              ? "submitted automatically when time ran out"
              : attempt.submissionReason === "STUDENT_SUBMITTED" || !attempt.autoSubmitted
                ? `submitted ${formatDateTime(attempt.submittedAt)}`
                : "submitted automatically by proctoring"}
          </p>
          {attempt.totalPenalty > 0 && (
            <p className="mt-1 text-sm text-red-700 tabular-nums">
              {attempt.rawScore} marks from your answers − {attempt.totalPenalty} for camera violations
            </p>
          )}
        </div>
      </div>
    </Card>

    {attempt.review ? (
      <Card>
        <CardHeader title="Review" description="Your answers next to the correct ones." />
        <ol className="divide-y divide-slate-100">
          {attempt.review.map((q, i) => {
            const right = q.yourAnswer === q.correctAnswer;
            return (
              <li key={q.id} className="flex gap-3 px-5 py-4">
                {right ? (
                  <CheckCircleIcon className="mt-0.5 size-5 shrink-0 text-emerald-600" aria-label="Correct" />
                ) : (
                  <XCircleIcon className="mt-0.5 size-5 shrink-0 text-red-500" aria-label="Incorrect" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-900">
                    <span className="mr-1.5 text-slate-400 tabular-nums">{i + 1}.</span>
                    {q.text}
                  </p>
                  <dl className="mt-2 space-y-1 text-[13px]">
                    <div className="flex gap-3">
                      <dt className="w-24 shrink-0 text-slate-500">Your answer</dt>
                      <dd className={right ? "text-slate-700" : "text-red-700"}>
                        {q.yourAnswer ? `${q.yourAnswer}. ${q.options[q.yourAnswer]}` : "Not answered"}
                      </dd>
                    </div>
                    {!right && (
                      <div className="flex gap-3">
                        <dt className="w-24 shrink-0 text-slate-500">Correct</dt>
                        <dd className="text-emerald-800">
                          {q.correctAnswer}. {q.options[q.correctAnswer]}
                        </dd>
                      </div>
                    )}
                  </dl>
                  {q.explanation && (
                    <p className="mt-2 text-[13px] leading-relaxed text-slate-500">
                      <span className="font-medium text-slate-700">Why: </span>
                      {q.explanation}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </Card>
    ) : (
      <Card className="p-5 text-sm text-slate-600">
        Correct answers and explanations appear here when the test closes at {formatClockTime(test.endsAt)}, once
        everyone has finished.
      </Card>
    )}
  </div>
);

const TakeTest = () => {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [sheet, setSheet] = useState(EMPTY_SHEET);
  const [index, setIndex] = useState(0);
  const [saveState, setSaveState] = useState("saved");
  const [starting, setStarting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const now = useServerClock(data?.serverTime);

  // Monitored tests: devices, full screen and warnings.
  const [stream, setStream] = useState(null);
  const [media, setMedia] = useState({ requesting: false, error: null });
  const [gateError, setGateError] = useState(null);
  const [session, setSession] = useState(false); // entered the monitored test on this page load
  const [warnings, setWarnings] = useState([]);
  const streamRef = useRef(null);
  const onSubmitted = useRef(null);
  const handleReport = useRef(null);

  // The newest answers live in a ref so saves and the final submit never send stale state.
  const latest = useRef(EMPTY_SHEET);
  const saver = useRef({
    busy: false,
    again: false,
    debounce: null,
    retry: null,
    stopped: false,
  });
  const submittingRef = useRef(false);
  const nextAutoSubmit = useRef(0);

  const apply = useCallback((payload) => {
    setData(payload);
    const { attempt } = payload;
    if (attempt?.status === "in_progress") {
      const restored = {
        answers: attempt.answers ?? {},
        review: attempt.review ?? [],
      };
      latest.current = restored;
      setSheet(restored);
      // Resume at the first unanswered question.
      const open = attempt.questions.findIndex((q) => !restored.answers[q.id]);
      setIndex(Math.max(open, 0));
    }
    if (attempt?.status === "submitted") onSubmitted.current?.();
  }, []);

  const load = useCallback(() => {
    setLoadError(null);
    api.get(`/me/tests/${id}`).then(({ data: payload }) => apply(payload), setLoadError);
  }, [id, apply]);

  useEffect(load, [load]);

  const rules = data?.attempt?.monitoring ?? data?.monitoring;
  const monitored = Boolean(rules?.enabled);
  const running = monitored && data?.attempt?.status === "in_progress" && session;
  const proctor = useProctoring({
    basePath: `/me/tests/${id}`,
    running,
    monitoring: rules,
    stream,
    getSheet: () => latest.current,
    onReport: (response) => handleReport.current(response),
    onRejected: () => load(),
  });
  const stopProctor = useRef(null);
  stopProctor.current = proctor.stop;

  const releaseDevices = () => {
    stopStream(streamRef.current);
    streamRef.current = null;
    exitFullscreen();
  };
  // Monitoring ends the moment the attempt is submitted, whoever submitted it.
  onSubmitted.current = () => {
    stopProctor.current?.();
    releaseDevices();
    setStream(null);
    setSession(false);
  };
  // Leaving the page: release the camera, microphone and full screen. (Not
  // stop(): leaving a running test mid-way is reported by the monitoring hook.)

  useEffect(() => () => releaseDevices(), []);

  handleReport.current = (response) => {
    const test = response.test;
    if (test?.attempt?.status === "submitted") {
      apply(test);
      return;
    }
    const monitoring = test?.attempt?.monitoring;
    if (monitoring) setData((d) => (d ? { ...d, attempt: { ...d.attempt, monitoring } } : d));
    const v = response.violation;
    // The blocking full-screen screen already explains a full-screen exit.
    if (!response.recorded || !v || !["warned", "penalised"].includes(v.actionTaken) || v.detail === "fullscreen_exit")
      return;
    const limit = monitoring?.limits?.[v.type] ?? 0;
    const warning = {
      id: newEventId(),
      type: v.type,
      severe: limit > 0 && limit - v.countAfter <= 1,
      ...describeViolation({
        type: v.type,
        detail: v.detail,
        count: v.countAfter,
        limit,
        penalty: v.penaltyApplied,
        totalPenalty: monitoring?.totalPenalty ?? 0,
      }),
    };
    setWarnings((list) => [...list.slice(-2), warning]);
  };

  // Each warning stays a while, then the oldest goes.
  useEffect(() => {
    if (!warnings.length) return undefined;
    const timer = setTimeout(() => setWarnings((list) => list.slice(1)), 12000);
    return () => clearTimeout(timer);
  }, [warnings]);

  // Reopened mid-test after leaving the page: report it (same event id as the
  // report sent while leaving, so it counts once).
  const pendingChecked = useRef(false);
  useEffect(() => {
    if (pendingChecked.current || !monitored || data?.attempt?.status !== "in_progress") return;
    pendingChecked.current = true;
    const pending = takePendingLeave(`/me/tests/${id}`);
    if (!pending) return;
    api
      .post(`/me/tests/${id}/violations`, { ...pending, ...latest.current })
      .then(({ data: response }) => handleReport.current(response))
      .catch(() => {});
  }, [monitored, data?.attempt?.status, id]);

  const requestDevices = async () => {
    setMedia({ requesting: true, error: null });
    try {
      const next = await requestMedia({
        camera: rules.cameraRequired,
        microphone: rules.microphoneRequired,
      });
      stopStream(streamRef.current);
      streamRef.current = next;
      setStream(next);
      setMedia({ requesting: false, error: null });
      if (running) proctor.report({ type: "technical", detail: "monitoring_resumed" });
    } catch (error) {
      setMedia({ requesting: false, error: mediaErrorMessage(error) });
    }
  };

  // Full screen first (it needs this click), then the test starts on the server.
  const enterExam = async ({ resume }) => {
    setGateError(null);
    if (rules.fullscreenRequired) {
      try {
        await enterFullscreen();
      } catch {
        setGateError(
          "Full screen didn't start, so the test hasn't started either. Allow full screen for this site and try again.",
        );
        return;
      }
    }
    if (resume) {
      setSession(true);
      return;
    }
    setStarting(true);
    try {
      const { data: payload } = await api.post(`/me/tests/${id}/start`);
      apply(payload);
      setSession(payload.attempt?.status === "in_progress");
    } catch (error) {
      exitFullscreen();
      toast.error(apiError(error, "Couldn't start the test."));
      load();
    } finally {
      setStarting(false);
    }
  };

  const returnToFullscreen = async () => {
    setGateError(null);
    try {
      await enterFullscreen();
    } catch {
      setGateError("Full screen was blocked. Try the button again.");
    }
  };

  // Autosave: one request at a time, always sending the newest answers.
  const flush = useCallback(async () => {
    const s = saver.current;
    clearTimeout(s.debounce);
    clearTimeout(s.retry);
    s.debounce = s.retry = null;
    if (s.busy) {
      s.again = true;
      return;
    }
    s.busy = true;
    try {
      do {
        s.again = false;
        await api.put(`/me/tests/${id}/answers`, latest.current);
      } while (s.again);
      if (!s.debounce) setSaveState("saved");
    } catch (error) {
      if (error.response?.status === 400) {
        load(); // already submitted, or time is up: show what the server has
      } else {
        setSaveState("error");
        if (!s.stopped) s.retry = setTimeout(flush, 3000);
      }
    } finally {
      s.busy = false;
    }
  }, [id, load]);

  // Leaving the page: send any change that hasn't been saved yet, then stop retrying.
  useEffect(() => {
    const s = saver.current;
    s.stopped = false;
    return () => {
      const pending = s.debounce || s.retry;
      clearTimeout(s.debounce);
      clearTimeout(s.retry);
      s.debounce = s.retry = null;
      s.stopped = true;
      if (pending) api.put(`/me/tests/${id}/answers`, latest.current).catch(() => {});
    };
  }, [id]);

  const change = useCallback(
    (update) => {
      latest.current = update(latest.current);
      setSheet(latest.current);
      setSaveState("saving");
      const s = saver.current;
      clearTimeout(s.debounce);
      s.debounce = setTimeout(flush, 500);
    },
    [flush],
  );

  const choose = useCallback(
    (qid, letter) => change((s) => ({ ...s, answers: { ...s.answers, [qid]: letter } })),
    [change],
  );

  const clearAnswer = (qid) =>
    change((s) => {
      const { [qid]: _removed, ...answers } = s.answers;
      return { ...s, answers };
    });

  const toggleReview = (qid) =>
    change((s) => ({
      ...s,
      review: s.review.includes(qid) ? s.review.filter((x) => x !== qid) : [...s.review, qid],
    }));

  const submit = useCallback(
    async (auto = false) => {
      if (submittingRef.current) return;
      submittingRef.current = true;
      const s = saver.current;
      clearTimeout(s.debounce);
      clearTimeout(s.retry);
      s.debounce = s.retry = null;
      setSubmitting(true);
      try {
        const { data: payload } = await api.post(`/me/tests/${id}/submit`, latest.current);
        setConfirming(false);
        setSaveState("saved");
        apply(payload);
        if (auto) toast("Time's up. Your answers were submitted.", { icon: "⏱️" });
        else toast.success("Test submitted");
      } catch (error) {
        toast.error(apiError(error, "Couldn't submit. Check your connection and try again."), { id: "submit-error" });
        if (!auto) flush(); // keep the answers safe even if they don't retry
      } finally {
        submittingRef.current = false;
        setSubmitting(false);
      }
    },
    [id, apply, flush],
  );

  const attempt = data?.attempt;
  const inProgress = attempt?.status === "in_progress";
  const questions = (inProgress && attempt.questions) || NO_QUESTIONS;
  const startsAt = data ? Date.parse(data.startsAt) : 0;
  const endsAt = data ? Date.parse(data.endsAt) : 0;
  const status = !data ? null : now < startsAt ? "scheduled" : now < endsAt ? "live" : "closed";
  const remaining = endsAt - now;
  const timeUp = inProgress && remaining <= 0;

  // Submit automatically when time runs out (and keep trying if the network is down).
  useEffect(() => {
    if (!timeUp || submittingRef.current || Date.now() < nextAutoSubmit.current) return;
    nextAutoSubmit.current = Date.now() + 5000;
    submit(true);
  }, [timeUp, remaining, submit]);

  // Submitted early: fetch the answer review once the test has closed for everyone.
  const awaitingReview = attempt?.status === "submitted" && !attempt.review && status === "closed";
  useEffect(() => {
    if (!awaitingReview) return undefined;
    const timer = setTimeout(load, 2000);
    return () => clearTimeout(timer);
  }, [awaitingReview, data, load]);

  // Warn before closing the tab with unsaved answers, or at all while monitored
  // (leaving the page counts as a screen switch).
  useEffect(() => {
    if (!inProgress || (saveState === "saved" && !running)) return undefined;
    const warn = (e) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [inProgress, saveState, running]);

  // Answers are frozen when time is up, while a limit is being submitted, or
  // until the student returns to full screen.
  const fullscreenLost = running && rules.fullscreenRequired && !proctor.fullscreen;
  const frozen = timeUp || proctor.submitting || fullscreenLost;

  useEffect(() => {
    if (fullscreenLost || proctor.submitting) setConfirming(false);
  }, [fullscreenLost, proctor.submitting]);

  // Keyboard: A–D (or 1–4) to answer, ← → to move between questions.
  useEffect(() => {
    if (!inProgress || confirming || frozen) return undefined;
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.target.closest?.("input, textarea, select, [contenteditable]"))
        return;
      const question = questions[index];
      const letter = LETTERS.includes(e.key.toUpperCase()) ? e.key.toUpperCase() : NUMBER_KEYS[e.key];
      if (letter && question?.options[letter] != null) choose(question.id, letter);
      else if (e.key === "ArrowRight") setIndex((i) => Math.min(i + 1, questions.length - 1));
      else if (e.key === "ArrowLeft") setIndex((i) => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [inProgress, confirming, frozen, questions, index, choose]);

  const start = async () => {
    setStarting(true);
    try {
      const { data: payload } = await api.post(`/me/tests/${id}/start`);
      apply(payload);
    } catch (error) {
      toast.error(apiError(error, "Couldn't start the test."));
      load();
    } finally {
      setStarting(false);
    }
  };

  if (loadError && !data) {
    const missing = loadError.response?.status === 404;
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="My tests" title={missing ? "Test not found" : "Test"} />
        {missing ? (
          <Card className="p-6 text-center text-sm text-slate-600">
            This test isn't assigned to you.{" "}
            <Link to="/tests" className="font-medium text-accent-700">
              Back to my tests
            </Link>
          </Card>
        ) : (
          <LoadError onRetry={load} />
        )}
      </div>
    );
  }
  if (!data) return <LoadingBlock className="h-64" />;

  // ---- Submitted: the result ----
  if (attempt.status === "submitted") {
    return (
      <div className="space-y-6">
        <Breadcrumb title={data.title} />
        <PageHeader
          title={data.title}
          description={`${data.audience.label} · ${formatDateTime(data.startsAt)} · ${data.questionCount} questions`}
        />
        <Result test={data} attempt={attempt} />
      </div>
    );
  }

  const needsMedia = monitored && (rules.cameraRequired || rules.microphoneRequired);
  const devicesReady =
    monitored && (!needsMedia || Boolean(stream)) && (!rules.fullscreenRequired || fullscreenSupported());
  const dismissWarning = (warningId) => setWarnings((list) => list.filter((w) => w.id !== warningId));

  // ---- Not started: scheduled, open, or missed ----
  if (!inProgress) {
    const missed = status === "closed";
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <Breadcrumb title={data.title} />
        <PageHeader
          title={data.title}
          description={data.subject || data.audience.label}
          actions={<TestStatusBadge status={status} />}
        />
        <Card>
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-t-lg bg-slate-100 sm:grid-cols-4">
            {[
              ["Opens", formatDateTime(data.startsAt)],
              ["Duration", formatDuration(data.durationMinutes)],
              ["Questions", data.questionCount],
              ["Marks", `${data.totalMarks} (${data.marksPerQuestion} each)`],
            ].map(([label, value]) => (
              <div key={label} className="bg-white px-5 py-4">
                <dt className="text-[12px] text-slate-500">{label}</dt>
                <dd className="mt-0.5 text-sm font-medium text-slate-900">{value}</dd>
              </div>
            ))}
          </dl>
          <div className="space-y-4 border-t border-slate-100 p-5 text-sm leading-relaxed text-slate-600">
            {data.instructions && <p className="whitespace-pre-line text-slate-800">{data.instructions}</p>}
            <ul className="list-disc space-y-1 pl-5 text-[13px]">
              <li>The timer can't be paused. The test closes for everyone at {formatClockTime(data.endsAt)}.</li>
              <li>Every question is multiple choice with one correct answer. Wrong answers don't lose marks.</li>
              <li>Answers save as you go. If you lose your connection, reopen this page to carry on.</li>
              <li>Whatever you've answered is submitted automatically when time runs out.</li>
            </ul>
          </div>
          {monitored && (
            <div className="space-y-5 border-t border-slate-100 p-5">
              <div>
                <h2 className="text-[15px] font-semibold text-slate-900">This test is proctored</h2>
                <p className="mt-0.5 text-[13px] text-slate-500">
                  Read the rules, then check your devices before you start.
                </p>
              </div>
              <MonitoringRules monitoring={rules} />
              {!missed && (
                <DeviceCheck
                  monitoring={rules}
                  stream={stream}
                  requesting={media.requesting}
                  error={media.error}
                  onRequest={requestDevices}
                />
              )}
              {gateError && (
                <p
                  role="alert"
                  className="rounded-lg bg-red-50 px-3 py-2.5 text-[13px] text-red-800 ring-1 ring-red-200"
                >
                  {gateError}
                </p>
              )}
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-b-lg border-t border-slate-100 bg-slate-50/70 px-5 py-4">
            {missed ? (
              <p className="text-sm text-slate-600">This test closed before you started it.</p>
            ) : status === "scheduled" ? (
              <p className="text-sm text-slate-600">
                Opens in{" "}
                <span className="font-mono font-semibold text-slate-900 tabular-nums">{countdown(startsAt - now)}</span>
              </p>
            ) : (
              <p className="text-sm text-slate-600">
                Closes in{" "}
                <span className="font-mono font-semibold text-slate-900 tabular-nums">{countdown(remaining)}</span>
                {remaining < data.durationMinutes * 60_000 && " (you get the time that's left)"}
              </p>
            )}
            {!missed &&
              (monitored ? (
                <Button
                  onClick={() => enterExam({ resume: false })}
                  loading={starting}
                  disabled={status !== "live" || !devicesReady}
                >
                  {rules.fullscreenRequired ? "Enter full screen and start" : "Start test"}
                  <ArrowRightIcon className="size-4" />
                </Button>
              ) : (
                <Button onClick={start} loading={starting} disabled={status !== "live"}>
                  Start test
                  <ArrowRightIcon className="size-4" />
                </Button>
              ))}
          </div>
        </Card>
      </div>
    );
  }

  // ---- In progress, monitored, but not entered on this page load (e.g. after a reload) ----
  if (monitored && !session) {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <Breadcrumb title={data.title} />
        <PageHeader title={data.title} description="Your test is in progress." actions={<Timer ms={remaining} />} />
        <Card>
          <div className="space-y-5 p-5">
            <div>
              <h2 className="text-[15px] font-semibold text-slate-900">Resume your test</h2>
              <p className="mt-0.5 text-[13px] leading-relaxed text-slate-500">
                Your answers are saved and the timer is still running.{" "}
                {needsMedia && "Turn your camera and microphone back on"}
                {needsMedia && rules.fullscreenRequired && " and "}
                {rules.fullscreenRequired && (needsMedia ? "return to full screen" : "Return to full screen")} to
                continue.
              </p>
            </div>
            <MonitoringRules monitoring={rules} />
            <DeviceCheck
              monitoring={rules}
              stream={stream}
              requesting={media.requesting}
              error={media.error}
              onRequest={requestDevices}
            />
            {gateError && (
              <p role="alert" className="rounded-lg bg-red-50 px-3 py-2.5 text-[13px] text-red-800 ring-1 ring-red-200">
                {gateError}
              </p>
            )}
          </div>
          <div className="flex justify-end rounded-b-lg border-t border-slate-100 bg-slate-50/70 px-5 py-4">
            <Button onClick={() => enterExam({ resume: true })} disabled={!devicesReady || timeUp}>
              {rules.fullscreenRequired ? "Return to full screen and continue" : "Continue the test"}
              <ArrowRightIcon className="size-4" />
            </Button>
          </div>
        </Card>
        <WarningStack warnings={warnings} onDismiss={dismissWarning} />
      </div>
    );
  }

  // ---- In progress: the test runner (the shared exam layout) ----
  const position = Math.min(index, questions.length - 1);
  const question = questions[position];
  const { answers, review } = sheet;
  const answeredCount = questions.filter((q) => answers[q.id]).length;
  const flagged = review.includes(question.id);
  const isLast = position === questions.length - 1;
  const minutesLeft = Math.ceil(remaining / 60_000);
  const announcement =
    remaining > 0 && ANNOUNCE_AT.includes(minutesLeft)
      ? `${minutesLeft} minute${minutesLeft === 1 ? "" : "s"} left`
      : "";
  const deviceLost =
    running && ((rules.cameraRequired && !proctor.cameraLive) || (rules.microphoneRequired && !proctor.micLive));

  return (
    <ExamShell
      title={data.title}
      icon={ClipboardDocumentListIcon}
      clock={{ remaining }}
      chips={monitored ? checkChips(rules) : []}
      actions={
        <>
          <SaveState state={saveState} />
          <Button onClick={() => setConfirming(true)} disabled={frozen}>
            Submit test
          </Button>
        </>
      }
      notices={
        <>
          {deviceLost && (
            <div
              role="alert"
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-amber-200"
            >
              <span>
                Your {rules.cameraRequired && !proctor.cameraLive ? "camera" : "microphone"} disconnected. Reconnect it
                to keep going
                {rules.cameraRequired &&
                  !proctor.cameraLive &&
                  "; after 30 seconds without a camera it counts as a camera violation"}
                .
              </span>
              <Button size="sm" variant="secondary" onClick={requestDevices} loading={media.requesting}>
                Reconnect
              </Button>
            </div>
          )}
          {media.error && running && (
            <p role="alert" className="text-[13px] text-red-700">
              {media.error}
            </p>
          )}
          {timeUp && (
            <div
              role="status"
              className="flex items-center gap-2 rounded-md bg-red-50 px-4 py-3 text-sm text-red-800 ring-1 ring-red-200"
            >
              <Spinner className="size-4" /> Time's up. Submitting your answers…
            </div>
          )}
        </>
      }
      sidebar={
        <QuestionList
          items={questions.map((q) => ({
            key: q.id,
            label: q.text,
            done: Boolean(answers[q.id]),
            flagged: review.includes(q.id),
          }))}
          current={position}
          onSelect={setIndex}
        />
      }
      panel={
        running && (
          <ProctorSidebar
            boxes={proctor.lastCheck?.phoneBoxes}
            stream={stream}
            rows={proctorStatuses({
              monitoring: rules,
              lastCheck: proctor.lastCheck,
              cameraLive: proctor.cameraLive,
              micLive: proctor.micLive,
              fullscreen: proctor.fullscreen,
            })}
          />
        )
      }
    >
      <Card>
        <QuestionHeader
          subject={data.subject || data.title}
          icon={ClipboardDocumentListIcon}
          position={position}
          total={questions.length}
          done={answeredCount}
        />
        <div className="space-y-6 p-5 sm:p-6">
          <QuestionTags
            tags={[
              `Question ${position + 1}`,
              `${data.marksPerQuestion} mark${data.marksPerQuestion === 1 ? "" : "s"}`,
            ]}
            action={<ReviewToggle flagged={flagged} onToggle={() => toggleReview(question.id)} disabled={frozen} />}
          />
          <h2
            id="question-text"
            className="text-xl leading-relaxed font-bold text-pretty whitespace-pre-line text-slate-900"
          >
            {question.text}
          </h2>
          <OptionList
            labelledBy="question-text"
            options={question.options}
            selected={answers[question.id]}
            onSelect={(letter) => choose(question.id, letter)}
            disabled={frozen}
          />
          {answers[question.id] && !frozen && (
            <button
              type="button"
              onClick={() => clearAnswer(question.id)}
              className="text-[13px] font-medium text-slate-500 hover:text-slate-800"
            >
              Clear answer
            </button>
          )}
        </div>
        <QuestionFooter
          position={position}
          total={questions.length}
          onPrevious={() => setIndex(position - 1)}
          onJump={setIndex}
          done={(i) => Boolean(answers[questions[i].id])}
          nextAction={
            isLast ? (
              <NextButton onClick={() => setConfirming(true)} disabled={frozen}>
                Review &amp; submit
              </NextButton>
            ) : (
              <NextButton onClick={() => setIndex(position + 1)} />
            )
          }
        />
      </Card>
      <p className="mt-3 hidden items-center justify-center gap-1 text-[12px] text-slate-400 sm:flex">
        <Kbd>A</Kbd>–<Kbd>D</Kbd> answer · <Kbd>←</Kbd>
        <Kbd>→</Kbd> move
      </p>

      {confirming && (
        <ConfirmSubmit
          answered={answeredCount}
          total={questions.length}
          flagged={review.length}
          submitting={submitting}
          onCancel={() => !submitting && setConfirming(false)}
          onConfirm={() => submit(false)}
        />
      )}
      {fullscreenLost && !proctor.submitting && (
        <FullscreenLost
          count={rules.counts?.screen_switch ?? 0}
          limit={rules.limits?.screen_switch ?? 0}
          error={gateError}
          onReturn={returnToFullscreen}
        />
      )}
      {proctor.submitting && <SubmittingOverlay />}
      {monitored && <WarningStack warnings={warnings} onDismiss={dismissWarning} />}
      <span className="sr-only" aria-live="polite">
        {announcement}
      </span>
    </ExamShell>
  );
};

export default TakeTest;
