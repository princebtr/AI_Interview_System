import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import toast from "react-hot-toast";
import { ArrowRightIcon, CheckCircleIcon, XCircleIcon } from "@heroicons/react/20/solid";
import { CircleStackIcon, ShieldCheckIcon } from "@heroicons/react/24/outline";
import api from "../utils/axios";
import { Button, Card, CardFooter, CardHeader, ChoiceChips, Input, Kbd, PageHeader } from "../components/ui";
import {
  DeviceCheck,
  FullscreenLost,
  MonitoringRules,
  ReasonBanner,
  SubmittingOverlay,
  WarningStack,
} from "../components/proctoring";
import {
  enterFullscreen,
  exitFullscreen,
  fullscreenSupported,
  mediaErrorMessage,
  requestMedia,
  stopStream,
  useProctoring,
} from "../hooks/useProctoring";
import { apiError, cx } from "../utils/helpers";
import {
  VIOLATION_LABELS,
  activeChecks,
  checkChips,
  describeViolation,
  newEventId,
  proctorStatuses,
} from "../utils/proctoring";
import { useElapsed } from "../hooks/useElapsed";
import {
  ExamShell,
  NextButton,
  OptionList,
  ProctorSidebar,
  QuestionFooter,
  QuestionHeader,
  QuestionList,
  QuestionTags,
  QuitButton,
} from "../components/exam";

const TOPICS = ["JavaScript", "Python", "Data structures", "SQL", "Operating systems", "Networking"];
const COUNTS = [5, 10, 15, 20];
const LETTERS = ["A", "B", "C", "D"];

const verdict = (pct) =>
  pct >= 80
    ? "Strong result. You know this topic well."
    : pct >= 50
      ? "Solid. Review the questions you missed below."
      : "Worth another pass. Review the misses, then retake.";

const ScoreRing = ({ value }) => {
  const r = 34;
  const circumference = 2 * Math.PI * r;
  const color = value >= 80 ? "text-emerald-600" : value >= 50 ? "text-amber-500" : "text-red-500";
  return (
    <div className="relative size-24 shrink-0">
      <svg viewBox="0 0 80 80" className="size-24 -rotate-90" aria-hidden="true">
        <circle cx="40" cy="40" r={r} fill="none" strokeWidth="6" className="stroke-slate-100" />
        <circle
          cx="40"
          cy="40"
          r={r}
          fill="none"
          strokeWidth="6"
          strokeLinecap="round"
          stroke="currentColor"
          className={cx(color, "transition-[stroke-dashoffset] duration-700")}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - value / 100)}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-xl font-semibold text-slate-900 tabular-nums">
        {Math.round(value)}%
      </span>
    </div>
  );
};

const Assessment = () => {
  // "Practise" links (areas to improve) open /assessment?subject=<subject>.
  const [params] = useSearchParams();
  const [subject, setSubject] = useState(() => (params.get("subject") ?? "").slice(0, 200));
  const [subjectError, setSubjectError] = useState("");
  const [count, setCount] = useState(10);
  const [questions, setQuestions] = useState([]);
  const [quizId, setQuizId] = useState(null);
  const [answers, setAnswers] = useState({});
  const [index, setIndex] = useState(0);
  const [results, setResults] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Proctoring: practice tests follow a default scheduled test's rules.
  const [rules, setRules] = useState(null); // rules and counts from the API
  const [started, setStarted] = useState(false); // entered the proctored session
  const [startedAt, setStartedAt] = useState(null);
  const [stream, setStream] = useState(null);
  const [media, setMedia] = useState({ requesting: false, error: null });
  const [gateError, setGateError] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [quitting, setQuitting] = useState(false);
  const streamRef = useRef(null);
  const answersRef = useRef({}); // newest answers, sent with every proctoring report
  const handleReport = useRef(null);
  const syncStatus = useRef(null);

  const proctored = Boolean(rules?.enabled);
  const stage = results ? "results" : !questions.length ? "setup" : proctored && !started ? "ready" : "taking";
  const running = proctored && stage === "taking";
  const elapsed = useElapsed(stage === "taking" ? startedAt : null);
  const current = questions[index];
  const answeredCount = questions.filter((q) => answers[String(q.id)]).length;
  const unanswered = questions.length - answeredCount;
  const isLast = index === questions.length - 1;

  const proctor = useProctoring({
    basePath: `/ai/practice/${quizId}`,
    running,
    monitoring: rules,
    stream,
    getSheet: () => ({ answers: answersRef.current }),
    onReport: (response) => handleReport.current(response),
    onRejected: () => syncStatus.current(),
  });
  const stopProctor = useRef(null);
  stopProctor.current = proctor.stop;

  const releaseDevices = () => {
    stopStream(streamRef.current);
    streamRef.current = null;
    setStream(null);
    exitFullscreen();
  };
  // Leaving the page releases the camera, microphone and full screen. (Leaving
  // mid-test is reported by the proctoring hook.)
  useEffect(
    () => () => {
      stopStream(streamRef.current);
      exitFullscreen();
    },
    [],
  );

  const setAnswer = useCallback((qid, letter) => {
    answersRef.current = { ...answersRef.current, [qid]: letter };
    setAnswers(answersRef.current);
  }, []);

  // A finished test: show the result and end the proctoring at once.
  const finish = (result) => {
    stopProctor.current?.();
    releaseDevices();
    setStarted(false);
    setQuitting(false);
    setWarnings([]);
    setResults(result);
    if (result.monitoring) setRules(result.monitoring);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // The server may have submitted the test already (a limit reached while a
  // response was lost): show what it has.
  syncStatus.current = async () => {
    if (!quizId) return false;
    try {
      const { data } = await api.get(`/ai/practice/${quizId}`);
      if (data.submitted && data.result) {
        finish(data.result);
        return true;
      }
      if (data.monitoring) setRules(data.monitoring);
    } catch {
      // Keep going; the next report or submission will try again.
    }
    return false;
  };

  handleReport.current = (response) => {
    if (response.submitted && response.result) {
      finish(response.result);
      return;
    }
    if (response.monitoring) setRules(response.monitoring);
    const v = response.violation;
    // The blocking full-screen screen already explains a full-screen exit.
    if (!response.recorded || !v || v.actionTaken !== "warned" || v.detail === "fullscreen_exit") return;
    const limit = response.monitoring?.limits?.[v.type] ?? 0;
    const warning = {
      id: newEventId(),
      type: v.type,
      severe: limit > 0 && limit - v.countAfter <= 1,
      ...describeViolation({
        type: v.type,
        detail: v.detail,
        count: v.countAfter,
        limit,
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

  const generate = async () => {
    const topic = subject.trim();
    if (!topic) {
      setSubjectError("Enter a subject to generate questions.");
      return;
    }
    setSubjectError("");
    setGenerating(true);
    try {
      const { data } = await api.post(
        "/ai/generate-mcq-questions",
        { subject: topic, numQuestions: count },
        { timeout: 60000 }, // the server retries busy AI models for up to ~50s
      );
      if (!data.questions?.length) throw new Error("empty");
      setSubject(topic);
      setQuizId(data.quizId);
      setQuestions(data.questions);
      setRules(data.monitoring ?? null);
      setStartedAt(data.monitoring?.enabled ? null : Date.now()); // unproctored: starts right away
      answersRef.current = {};
      setAnswers({});
      setIndex(0);
      setResults(null);
      setStarted(false);
      setGateError(null);
    } catch (error) {
      toast.error(apiError(error, "Couldn't generate questions. Try a different subject."));
    } finally {
      setGenerating(false);
    }
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      // Graded on the server against answer keys this page never receives.
      const { data } = await api.post("/ai/evaluate-mcq-answers", {
        quizId,
        userAnswers: answersRef.current,
      });
      finish(data);
    } catch (error) {
      if (error.response?.status === 400 && (await syncStatus.current())) return;
      toast.error(apiError(error, "Couldn't score your answers. Try again."));
    } finally {
      setSubmitting(false);
    }
  };

  const reset = () => {
    stopProctor.current?.();
    releaseDevices();
    setQuestions([]);
    setQuizId(null);
    answersRef.current = {};
    setAnswers({});
    setResults(null);
    setIndex(0);
    setRules(null);
    setStarted(false);
    setQuitting(false);
    setWarnings([]);
    setGateError(null);
  };

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

  // Full screen needs this click; the test starts only once it succeeds.
  const enter = async () => {
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
    setStarted(true);
    setStartedAt(Date.now());
  };

  const returnToFullscreen = async () => {
    setGateError(null);
    try {
      await enterFullscreen();
    } catch {
      setGateError("Full screen was blocked. Try the button again.");
    }
  };

  const needsMedia = proctored && (rules.cameraRequired || rules.microphoneRequired);
  const devicesReady =
    proctored && (!needsMedia || Boolean(stream)) && (!rules.fullscreenRequired || fullscreenSupported());
  const fullscreenLost = running && rules.fullscreenRequired && !proctor.fullscreen;
  const frozen = proctor.submitting || fullscreenLost;
  const deviceLost =
    running && ((rules.cameraRequired && !proctor.cameraLive) || (rules.microphoneRequired && !proctor.micLive));

  // Keyboard: A–D or 1–4 to answer, arrows to move between questions.
  useEffect(() => {
    if (stage !== "taking" || frozen) return undefined;
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.target.closest?.("input, textarea")) return;
      const letter = LETTERS.includes(e.key.toUpperCase())
        ? e.key.toUpperCase()
        : LETTERS[["1", "2", "3", "4"].indexOf(e.key)];
      if (letter) {
        setAnswer(String(questions[index].id), letter);
      } else if (e.key === "ArrowRight") {
        setIndex((i) => Math.min(i + 1, questions.length - 1));
      } else if (e.key === "ArrowLeft") {
        setIndex((i) => Math.max(i - 1, 0));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stage, frozen, questions, index, setAnswer]);

  // Leaving the page mid-test counts as a screen switch: ask first.
  useEffect(() => {
    if (!running) return undefined;
    const warn = (e) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [running]);

  const optionText = (result, letter) => result.options?.[letter] ?? "";
  const dismissWarning = (warningId) => setWarnings((list) => list.filter((w) => w.id !== warningId));

  const quizCard = current && (
    <Card>
      <QuestionHeader
        subject={subject}
        icon={CircleStackIcon}
        position={index}
        total={questions.length}
        done={answeredCount}
      />
      <div className="space-y-6 p-5 sm:p-6">
        <QuestionTags tags={[`Question ${index + 1}`, subject]} />
        <h2 id="practice-question" className="text-xl leading-relaxed font-bold text-pretty text-slate-900">
          {current.question}
        </h2>
        <OptionList
          labelledBy="practice-question"
          options={current.options}
          selected={answers[String(current.id)]}
          onSelect={(letter) => setAnswer(String(current.id), letter)}
          disabled={frozen}
        />
      </div>
      <QuestionFooter
        position={index}
        total={questions.length}
        onPrevious={() => setIndex((i) => i - 1)}
        onJump={setIndex}
        done={(i) => Boolean(answers[String(questions[i].id)])}
        nextAction={
          isLast ? (
            <NextButton onClick={submit} loading={submitting} disabled={unanswered > 0 || frozen}>
              {unanswered > 0 ? `${unanswered} unanswered` : "Submit test"}
            </NextButton>
          ) : (
            <NextButton onClick={() => setIndex((i) => i + 1)} />
          )
        }
      />
    </Card>
  );

  const keyHints = (
    <p className="mt-3 hidden items-center justify-center gap-1.5 text-[12px] text-slate-400 sm:flex">
      <Kbd>A</Kbd>–<Kbd>D</Kbd> to answer
      <span className="mx-1.5 text-slate-300">·</span>
      <Kbd>←</Kbd>
      <Kbd>→</Kbd> to move
    </p>
  );

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Practice"
        title="Practice test"
        description="Multiple-choice questions on any topic, scored instantly and proctored like a real test. Your results count towards your performance."
        actions={
          stage === "ready" && (
            <Button variant="ghost" onClick={reset}>
              Start over
            </Button>
          )
        }
      />

      {stage === "setup" && (
        <Card className="max-w-2xl">
          <CardHeader title="New assessment" description="Choose a topic and how many questions you want." />
          <form
            noValidate
            onSubmit={(e) => {
              e.preventDefault();
              generate();
            }}
          >
            <div className="space-y-6 p-5">
              <div className="space-y-3">
                <Input
                  id="mcq-subject"
                  label="Subject"
                  placeholder="e.g. JavaScript closures, TCP/IP, SQL joins"
                  value={subject}
                  maxLength={200}
                  error={subjectError}
                  onChange={(e) => setSubject(e.target.value)}
                />
                <ChoiceChips options={TOPICS} value={subject} onChange={setSubject} />
              </div>

              <fieldset>
                <legend className="mb-1.5 text-sm font-semibold text-slate-700">Number of questions</legend>
                <div className="inline-flex rounded-md border border-slate-200 bg-slate-100 p-0.5">
                  {COUNTS.map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setCount(n)}
                      aria-pressed={count === n}
                      className={cx(
                        "h-8 min-w-12 rounded px-3 text-sm font-medium tabular-nums transition-colors",
                        count === n
                          ? "bg-white text-slate-900 shadow-xs ring-1 ring-slate-200"
                          : "text-slate-500 hover:text-slate-800",
                      )}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </fieldset>

              <p className="flex gap-2 rounded-lg bg-accent-50/60 px-3 py-2.5 text-[13px] leading-relaxed text-slate-600 ring-1 ring-accent-100">
                <ShieldCheckIcon className="size-4 shrink-0 text-accent-600" />
                <span>
                  Practice tests are proctored like real tests: full screen, camera and microphone checks. You'll see
                  the rules and check your devices before you start.
                </span>
              </p>
            </div>
            <CardFooter>
              <p className="text-[13px] text-slate-500">Takes about {count} minutes.</p>
              <Button type="submit" loading={generating}>
                {generating ? `Generating ${count} questions` : "Generate questions"}
              </Button>
            </CardFooter>
          </form>
        </Card>
      )}

      {stage === "ready" && (
        <Card className="max-w-2xl">
          <CardHeader
            title={`${subject}: ${questions.length} questions`}
            description="This practice test is proctored. Read the rules, then check your devices before you start."
          />
          <div className="space-y-5 p-5">
            <MonitoringRules monitoring={rules} practice />
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
          <CardFooter>
            <Button variant="ghost" onClick={reset}>
              Cancel
            </Button>
            <Button onClick={enter} disabled={!devicesReady}>
              {rules.fullscreenRequired ? "Enter full screen and start" : "Start test"}
              <ArrowRightIcon className="size-4" />
            </Button>
          </CardFooter>
        </Card>
      )}

      {stage === "taking" && current && (
        <ExamShell
          title={`Practice test: ${subject}`}
          icon={CircleStackIcon}
          clock={{ elapsed }}
          chips={proctored ? checkChips(rules) : []}
          actions={
            quitting ? (
              <span className="flex items-center gap-2">
                <span className="text-[13px] text-slate-600">Quit? It won't be scored.</span>
                <Button size="sm" variant="danger" onClick={reset}>
                  Quit
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setQuitting(false)}>
                  Keep going
                </Button>
              </span>
            ) : (
              <QuitButton onClick={() => setQuitting(true)} />
            )
          }
          notices={
            <>
              {deviceLost && (
                <div
                  role="alert"
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-amber-200"
                >
                  <span>
                    Your {rules.cameraRequired && !proctor.cameraLive ? "camera" : "microphone"} disconnected. Reconnect
                    it to keep going
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
              {media.error && (
                <p role="alert" className="text-[13px] text-red-700">
                  {media.error}
                </p>
              )}
            </>
          }
          sidebar={
            <QuestionList
              items={questions.map((q) => ({
                key: q.id,
                label: q.question,
                done: Boolean(answers[String(q.id)]),
              }))}
              current={index}
              onSelect={setIndex}
            />
          }
          panel={
            proctored && (
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
          {quizCard}
          {keyHints}
          {fullscreenLost && !proctor.submitting && (
            <FullscreenLost
              count={rules.counts?.screen_switch ?? 0}
              limit={rules.limits?.screen_switch ?? 0}
              error={gateError}
              onReturn={returnToFullscreen}
            />
          )}
          {proctor.submitting && <SubmittingOverlay />}
          <WarningStack warnings={warnings} onDismiss={dismissWarning} />
        </ExamShell>
      )}

      {stage === "results" && (
        <div className="max-w-3xl space-y-6">
          <ReasonBanner reason={results.submissionReason} practice />
          <Card>
            <div className="flex flex-col gap-6 p-6 sm:flex-row sm:items-center">
              <ScoreRing value={results.percentage} />
              <div className="min-w-0">
                <p className="text-[13px] font-medium text-slate-500">{subject}</p>
                <p className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">
                  {results.score} of {results.totalQuestions} correct
                </p>
                <p className="mt-1 text-sm text-slate-500">{verdict(results.percentage)}</p>
                {results.monitoring?.enabled && (
                  <p className="mt-1 text-[13px] text-slate-500">
                    Proctoring:{" "}
                    {activeChecks(results.monitoring)
                      .map((type) => `${VIOLATION_LABELS[type]} ${results.monitoring.counts?.[type] ?? 0}`)
                      .join(" · ")}
                  </p>
                )}
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button onClick={generate} loading={generating}>
                    Retake with new questions
                  </Button>
                  <Button variant="secondary" onClick={reset}>
                    Change topic
                  </Button>
                </div>
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader title="Review" description="Your answer next to the correct one." />
            <ol className="divide-y divide-slate-100">
              {results.results.map((r, i) => (
                <li key={r.questionId} className="flex gap-3 px-5 py-4">
                  {r.isCorrect ? (
                    <CheckCircleIcon className="mt-0.5 size-5 shrink-0 text-emerald-600" aria-label="Correct" />
                  ) : (
                    <XCircleIcon className="mt-0.5 size-5 shrink-0 text-red-500" aria-label="Incorrect" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-900">
                      <span className="mr-1.5 text-slate-400 tabular-nums">{i + 1}.</span>
                      {r.question}
                    </p>
                    <dl className="mt-2 space-y-1 text-[13px]">
                      <div className="flex gap-3">
                        <dt className="w-24 shrink-0 text-slate-500">Your answer</dt>
                        <dd className={r.isCorrect ? "text-slate-700" : "text-red-700"}>
                          {r.userAnswer ? `${r.userAnswer}. ${optionText(r, r.userAnswer)}` : "No answer"}
                        </dd>
                      </div>
                      {!r.isCorrect && (
                        <div className="flex gap-3">
                          <dt className="w-24 shrink-0 text-slate-500">Correct</dt>
                          <dd className="text-emerald-800">
                            {r.correctAnswer}. {optionText(r, r.correctAnswer)}
                          </dd>
                        </div>
                      )}
                    </dl>
                    {r.explanation && (
                      <p className="mt-2 text-[13px] leading-relaxed text-slate-500">
                        <span className="font-medium text-slate-700">Why: </span>
                        {r.explanation}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      )}
    </div>
  );
};

export default Assessment;
