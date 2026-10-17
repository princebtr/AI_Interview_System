import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { ArrowPathIcon, ArrowRightIcon, MicrophoneIcon, StopIcon } from "@heroicons/react/20/solid";
import { ShieldCheckIcon, VideoCameraIcon } from "@heroicons/react/24/outline";
import api from "../utils/axios";
import {
  Badge,
  Button,
  Card,
  CardFooter,
  CardHeader,
  ChoiceChips,
  Input,
  PageHeader,
  Textarea,
} from "../components/ui";
import { DeviceCheck, FullscreenLost, WarningStack } from "../components/proctoring";
import { ExamShell, ProctorSidebar, QuestionHeader, QuestionList, QuestionTags, QuitButton } from "../components/exam";
import {
  enterFullscreen,
  exitFullscreen,
  fullscreenSupported,
  mediaErrorMessage,
  requestMedia,
  stopStream,
} from "../hooks/useProctoring";
import { useInterviewProctoring } from "../hooks/useInterviewProctoring";
import { useElapsed } from "../hooks/useElapsed";
import { apiError } from "../utils/helpers";
import { newEventId, proctorStatuses } from "../utils/proctoring";

// The server retries busy AI models for up to ~50s before giving up.
const AI_TIMEOUT = { timeout: 60000 };

const TOPICS = ["React", "JavaScript", "Python", "System design", "SQL", "Behavioral"];

// What an interview checks (answers are spoken, so there's no speech check).
const RULES = {
  enabled: true,
  cameraRequired: true,
  phoneDetection: true,
  microphoneRequired: false,
  fullscreenRequired: true,
};

const ISSUE_TEXT = {
  screen_switch: ["Full screen", "You left full-screen mode."],
  face: ["Camera", "No one, or more than one person, was visible in the camera."],
  phone: ["Phone", "A possible mobile phone was detected. Put it away."],
  tabs: ["Tab switch", "You switched to another tab or app. Stay on the interview."],
};

// Gemini sometimes wraps text in markdown emphasis.
const plain = (text) => text.replace(/\*\*|__/g, "").trim();

const scoreTone = (score) => (score >= 7 ? "success" : score >= 4 ? "warning" : "danger");

const QuestionSkeleton = () => (
  <div className="space-y-2.5" aria-label="Loading question">
    <div className="h-5 w-11/12 animate-pulse rounded bg-slate-100" />
    <div className="h-5 w-3/4 animate-pulse rounded bg-slate-100" />
  </div>
);

const Interview = () => {
  const [subject, setSubject] = useState("");
  const [subjectError, setSubjectError] = useState("");
  const [active, setActive] = useState(false);
  const [question, setQuestion] = useState("");
  const [questionId, setQuestionId] = useState(null);
  const [answer, setAnswer] = useState("");
  const [history, setHistory] = useState([]);
  const [loadingQuestion, setLoadingQuestion] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef(null);

  // Proctoring: camera, full screen, tab switches.
  const [stream, setStream] = useState(null);
  const [media, setMedia] = useState({ requesting: false, error: null });
  const [gateError, setGateError] = useState(null);
  const [startedAt, setStartedAt] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const streamRef = useRef(null);
  const elapsed = useElapsed(active ? startedAt : null);

  const proctor = useInterviewProctoring({
    active,
    stream,
    onIssue: (kind, count) => {
      if (kind === "screen_switch") return; // the blocking screen explains it
      const [title, message] = ISSUE_TEXT[kind];
      setWarnings((list) => [
        ...list.slice(-2),
        {
          id: newEventId(),
          type: kind === "tabs" ? "screen_switch" : kind,
          title,
          message,
          progress: `This has happened ${count} time${count === 1 ? "" : "s"} this session.`,
        },
      ]);
    },
  });

  const releaseDevices = () => {
    stopStream(streamRef.current);
    streamRef.current = null;
    setStream(null);
    exitFullscreen();
  };

  useEffect(
    () => () => {
      recognitionRef.current?.abort();
      stopStream(streamRef.current);
      exitFullscreen();
    },
    [],
  );

  // Each warning stays a while, then the oldest goes.
  useEffect(() => {
    if (!warnings.length) return undefined;
    const timer = setTimeout(() => setWarnings((list) => list.slice(1)), 10000);
    return () => clearTimeout(timer);
  }, [warnings]);

  const fetchQuestion = async (topic) => {
    setLoadingQuestion(true);
    try {
      const { data } = await api.post("/ai/generate-question", { subject: topic }, AI_TIMEOUT);
      setQuestion(plain(data.question));
      setQuestionId(data.questionId);
      setAnswer("");
      return true;
    } catch (error) {
      toast.error(apiError(error, "Couldn't generate a question. Try again."));
      return false;
    } finally {
      setLoadingQuestion(false);
    }
  };

  const requestDevices = async () => {
    setMedia({ requesting: true, error: null });
    try {
      const next = await requestMedia({ camera: true, microphone: false });
      stopStream(streamRef.current);
      streamRef.current = next;
      setStream(next);
      setMedia({ requesting: false, error: null });
    } catch (error) {
      setMedia({ requesting: false, error: mediaErrorMessage(error) });
    }
  };

  // Full screen first (it needs this click), then the first question.
  const startSession = async (e) => {
    e.preventDefault();
    const topic = subject.trim();
    if (!topic) {
      setSubjectError("Enter a subject to practice.");
      return;
    }
    setSubjectError("");
    setGateError(null);
    try {
      await enterFullscreen();
    } catch {
      setGateError(
        "Full screen didn't start, so the session hasn't started either. Allow full screen for this site and try again.",
      );
      return;
    }
    if (await fetchQuestion(topic)) {
      setSubject(topic);
      setHistory([]);
      setWarnings([]);
      setStartedAt(Date.now());
      setActive(true);
      // Registers the session for the institution's records (no snapshot is kept).
      api
        .post("/ai/session", new FormData(), {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .catch(() => {});
    } else {
      exitFullscreen();
    }
  };

  const stopListening = () => recognitionRef.current?.stop();

  const endSession = () => {
    proctor.stop();
    stopListening();
    releaseDevices();
    setActive(false);
    setQuestion("");
    setQuestionId(null);
    setAnswer("");
    setWarnings([]);
  };

  const returnToFullscreen = async () => {
    setGateError(null);
    try {
      await enterFullscreen();
    } catch {
      setGateError("Full screen was blocked. Try the button again.");
    }
  };

  const toggleListening = () => {
    if (listening) {
      stopListening();
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      toast.error("Voice input isn't supported in this browser. Try Chrome or Edge.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.interimResults = true;
    recognition.continuous = true;
    const prefix = answer.trim() ? `${answer.trim()} ` : "";

    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0].transcript)
        .join("");
      setAnswer(prefix + transcript);
    };
    recognition.onerror = (event) => {
      if (!["aborted", "no-speech"].includes(event.error)) {
        toast.error(`Voice input stopped: ${event.error}`);
      }
    };
    recognition.onend = () => setListening(false);

    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  };

  const submitAnswer = async () => {
    const text = answer.trim();
    if (!text) return;
    stopListening();
    setEvaluating(true);
    try {
      const { data } = await api.post("/ai/evaluate-answer", { questionId, answer: text }, AI_TIMEOUT);
      const score = Number(data.evaluation);
      setHistory((h) => [{ question, answer: text, score }, ...h]);
      toast.success(`Scored ${score}/10`);
      await fetchQuestion(subject);
    } catch (error) {
      toast.error(apiError(error, "Couldn't evaluate your answer. Try again."));
    } finally {
      setEvaluating(false);
    }
  };

  const average = history.length ? history.reduce((sum, h) => sum + h.score, 0) / history.length : 0;
  const fullscreenLost = active && !proctor.fullscreen;
  const devicesReady = Boolean(stream) && fullscreenSupported();

  const historyCard = history.length > 0 && (
    <Card>
      <CardHeader
        title={active ? "This session" : "Last session"}
        description={`${history.length} answered · average ${average.toFixed(1)} / 10`}
      />
      <ol className="divide-y divide-slate-100">
        {history.map((item, i) => (
          <li key={history.length - i} className="flex items-start gap-4 px-5 py-4">
            <span className="mt-0.5 w-5 shrink-0 text-[13px] text-slate-400 tabular-nums">{history.length - i}</span>
            <div className="min-w-0 flex-1">
              <p className="line-clamp-2 text-sm font-medium text-slate-900">{item.question}</p>
              <p className="mt-1 line-clamp-2 text-[13px] text-slate-500">{item.answer}</p>
            </div>
            <Badge tone={scoreTone(item.score)} className="tabular-nums">
              {item.score} / 10
            </Badge>
          </li>
        ))}
      </ol>
    </Card>
  );

  if (active) {
    const asked = [...history].reverse();
    const rows = [
      ...proctorStatuses({
        monitoring: RULES,
        lastCheck: proctor.lastCheck,
        cameraLive: Boolean(stream),
        fullscreen: proctor.fullscreen,
      }),
      {
        key: "tabs",
        label: "Tab switches",
        ...(proctor.counts.tabs ? { state: "warn", text: `${proctor.counts.tabs}×` } : { state: "ok", text: "None" }),
      },
    ];
    return (
      <ExamShell
        title={`AI interview: ${subject}`}
        icon={VideoCameraIcon}
        clock={{ elapsed }}
        chips={["screen_switch", "face", "phone", "tabs"].map((key) => ({
          key,
          count: proctor.counts[key],
          limit: 0,
        }))}
        actions={<QuitButton onClick={endSession}>End session</QuitButton>}
        sidebar={
          <QuestionList
            items={[
              ...asked.map((h, i) => ({
                key: i,
                label: h.question,
                badge: (
                  <Badge tone={scoreTone(h.score)} className="tabular-nums">
                    {h.score}/10
                  </Badge>
                ),
              })),
              {
                key: "current",
                label: loadingQuestion ? "Next question…" : question,
              },
            ]}
            current={asked.length}
          />
        }
        panel={
          <ProctorSidebar
            boxes={proctor.lastCheck?.phoneBoxes}
            stream={stream}
            rows={rows}
            note="Checks run every few seconds. Nothing is recorded; your answers are scored by AI."
          />
        }
      >
        <div className="space-y-5">
          <Card>
            <QuestionHeader subject={subject} icon={VideoCameraIcon} position={history.length} total={0} />
            <div className="space-y-6 p-5 sm:p-6">
              <QuestionTags
                tags={[`Question ${history.length + 1}`, "Scored out of 10"]}
                action={
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => fetchQuestion(subject)}
                    disabled={loadingQuestion || evaluating}
                  >
                    <ArrowPathIcon className="size-4" />
                    Skip
                  </Button>
                }
              />
              {loadingQuestion ? (
                <QuestionSkeleton />
              ) : (
                <h2 className="text-xl leading-relaxed font-bold text-pretty text-slate-900">{question}</h2>
              )}
              <Textarea
                id="answer"
                label="Your answer"
                rows={7}
                value={answer}
                disabled={evaluating || fullscreenLost}
                placeholder="Type your answer, or dictate it with the microphone."
                onChange={(e) => setAnswer(e.target.value)}
                action={
                  listening && (
                    <span className="flex items-center gap-1.5 text-[12px] font-medium text-red-600">
                      <span className="size-1.5 animate-pulse rounded-full bg-red-500" />
                      Listening
                    </span>
                  )
                }
              />
            </div>
            <div className="flex flex-col gap-3 border-t border-slate-100 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
              <Button variant="secondary" size="lg" onClick={toggleListening} disabled={evaluating}>
                {listening ? (
                  <>
                    <StopIcon className="size-4 text-red-600" />
                    Stop dictation
                  </>
                ) : (
                  <>
                    <MicrophoneIcon className="size-4 text-slate-500" />
                    Dictate
                  </>
                )}
              </Button>
              <Button
                size="lg"
                onClick={submitAnswer}
                loading={evaluating}
                disabled={!answer.trim() || loadingQuestion || fullscreenLost}
              >
                Submit answer
                <ArrowRightIcon className="size-4" />
              </Button>
            </div>
          </Card>
          {historyCard}
        </div>
        {fullscreenLost && (
          <FullscreenLost
            count={proctor.counts.screen_switch}
            limit={0}
            error={gateError}
            onReturn={returnToFullscreen}
          />
        )}
        <WarningStack warnings={warnings} onDismiss={(id) => setWarnings((list) => list.filter((w) => w.id !== id))} />
      </ExamShell>
    );
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Practice"
        title="AI interview"
        description="Answer one question at a time, out loud or in writing. Each answer is scored out of 10, and the session is proctored like a test."
      />

      <div className="max-w-2xl space-y-6">
        <Card>
          <CardHeader
            title={history.length ? "Start another session" : "Set up your session"}
            description="Pick a topic. Questions adapt to whatever you enter."
          />
          <form onSubmit={startSession} noValidate>
            <div className="space-y-5 p-5">
              <div className="space-y-3">
                <Input
                  id="subject"
                  label="Subject"
                  placeholder="e.g. React hooks, system design, leadership"
                  value={subject}
                  maxLength={200}
                  error={subjectError}
                  onChange={(e) => setSubject(e.target.value)}
                />
                <ChoiceChips options={TOPICS} value={subject} onChange={setSubject} />
              </div>
              <p className="flex gap-2 rounded-lg bg-accent-50/60 px-3 py-2.5 text-[13px] leading-relaxed text-slate-600 ring-1 ring-accent-100">
                <ShieldCheckIcon className="size-4 shrink-0 text-accent-600" />
                <span>
                  The session runs in full screen with camera checks (people in frame and phones). Leaving full screen
                  or switching tabs is counted. Nothing is recorded.
                </span>
              </p>
              <DeviceCheck
                monitoring={RULES}
                stream={stream}
                requesting={media.requesting}
                error={media.error}
                onRequest={requestDevices}
              />
              {gateError && (
                <p
                  role="alert"
                  className="rounded-lg bg-red-50 px-3 py-2.5 text-[13px] text-red-800 ring-1 ring-red-200"
                >
                  {gateError}
                </p>
              )}
            </div>
            <CardFooter>
              <p className="text-[13px] text-slate-500">Starts in full screen.</p>
              <Button type="submit" loading={loadingQuestion} disabled={!devicesReady}>
                Enter full screen and start
                <ArrowRightIcon className="size-4" />
              </Button>
            </CardFooter>
          </form>
        </Card>
        {historyCard}
      </div>
    </div>
  );
};

export default Interview;
