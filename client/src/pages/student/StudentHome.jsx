import { Link, useNavigate } from "react-router-dom";
import {
  CalendarDaysIcon,
  ChartBarIcon,
  ChatBubbleLeftRightIcon,
  ClipboardDocumentCheckIcon,
  FireIcon,
  MicrophoneIcon,
  VideoCameraIcon,
} from "@heroicons/react/24/outline";
import { useAuth } from "../../context/AuthContext";
import { useApi } from "../../hooks/useApi";
import { useServerClock } from "../../hooks/useServerClock";
import { ArrowIcon, Badge, Button, Card, CardHeader, GlowBackdrop, PageHeader } from "../../components/ui";
import { buttonStyles } from "../../components/styles";
import { CardLink, EmptyState, LoadError, LoadingBlock, ScoreBar, StatCard, StatGrid } from "../../components/data";
import { PracticeTopicLinks, StudentTestCard } from "../../components/tests";
import { cx } from "../../utils/helpers";
import { formatPercent } from "../../utils/scores";
import { firstName, timeAgo, todayLabel } from "../../utils/time";
import { KIND_META } from "../../utils/board";

const KIND_LABEL = { mcq: "Practice test", interview: "AI interview answer" };

// Icon tiles: the primary colour, or the secondary to tell a second option apart.
const TILE_TONES = {
  primary: "bg-accent-50 text-accent-700 ring-accent-100",
  secondary: "bg-accent2-50 text-accent2-700 ring-accent2-100",
};

const PracticeCard = ({ icon: Icon, tone = "primary", title, description, meta, to, action }) => (
  <Card interactive className="flex flex-col p-5">
    {Icon && (
      <span className={cx("flex size-12 items-center justify-center rounded-lg ring-1", TILE_TONES[tone])}>
        <Icon className="size-6" />
      </span>
    )}
    <p className="mt-4 text-base font-semibold text-slate-900">{title}</p>
    <p className="mt-1 flex-1 text-[13px] leading-relaxed text-slate-500">{description}</p>
    <div className="mt-5 flex items-center justify-between gap-3">
      <span className="text-[12px] text-slate-400">{meta}</span>
      <Link to={to} className={buttonStyles()}>
        {action}
        <ArrowIcon />
      </Link>
    </div>
  </Card>
);

// Its own component so the once-a-second clock only re-renders the test cards.
/** The three latest notes and messages shared with the student. Hidden until there is one. */
const LatestPosts = () => {
  const { data } = useApi("/board/posts", { limit: 3 });
  const posts = data?.posts ?? [];
  if (posts.length === 0) return null;
  return (
    <Card>
      <CardHeader
        title="From your educators"
        description="Latest notes and messages"
        action={<CardLink to="/board">All notes & messages</CardLink>}
      />
      <ul className="divide-y divide-slate-100">
        {posts.map((post) => (
          <li key={post.id}>
            <Link to="/board" className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-slate-50">
              <ChatBubbleLeftRightIcon className="size-5 shrink-0 text-slate-400" />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium text-slate-900">{post.title}</span>
                  {!post.read && <span className="size-1.5 shrink-0 rounded-full bg-accent-600" aria-label="New" />}
                </span>
                <span className="block text-[12px] text-slate-500">
                  {KIND_META[post.kind].label} · {post.author?.name ?? "Staff"} · {timeAgo(post.createdAt)}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
};

const UpNextTests = () => {
  const { data, error, reload } = useApi("/me/tests");
  const now = useServerClock(data?.serverTime);
  const tests = data?.tests ?? [];
  // Live and upcoming tests the student still has to sit, soonest first (max 3).
  const upNext = tests
    .filter((t) => new Date(t.endsAt).getTime() > now && t.attempt.status !== "submitted")
    .slice(0, 3);

  return (
    <>
      <div className="flex items-center justify-between">
        <h2 id="next-heading" className="text-sm font-semibold text-slate-900">
          Up next
        </h2>
        {tests.length > 0 && <CardLink to="/tests">All tests</CardLink>}
      </div>
      {error && !data ? (
        <LoadError onRetry={reload} />
      ) : !data ? (
        <LoadingBlock className="h-24" />
      ) : upNext.length > 0 ? (
        upNext.map((t) => <StudentTestCard key={t.id} test={t} now={now} />)
      ) : (
        <Card className="flex items-start gap-4 p-5">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-slate-100 text-slate-500">
            <CalendarDaysIcon className="size-5" />
          </span>
          <div>
            <p className="text-sm font-medium text-slate-900">
              {tests.length ? "No upcoming tests" : "No tests assigned yet"}
            </p>
            <p className="mt-0.5 text-[13px] leading-relaxed text-slate-500">
              When your educators assign a test, it shows up here with its start time and duration.
              Until then, keep practising below.
            </p>
          </div>
        </Card>
      )}
    </>
  );
};

const StudentHome = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data } = useApi("/me/performance");
  const summary = data?.summary;
  const hasPractice = (summary?.attempts ?? 0) > 0;

  return (
    <div className="relative isolate space-y-8">
      <GlowBackdrop className="-inset-x-4 -top-8 h-96 sm:-inset-x-6 lg:-inset-x-10 lg:-top-10" />
      <PageHeader
        eyebrow={todayLabel()}
        title={
          <>
            Hello, <span className="text-accent-600">{firstName(user?.name)}</span>
          </>
        }
        description={
          user?.placement ? `${user.placement.label} · ${user.institution?.name ?? ""}` : "Here's what's next for you."
        }
      />

      <section className="space-y-3" aria-labelledby="next-heading">
        <UpNextTests />
        <LatestPosts />
        <div className="grid gap-4 md:grid-cols-2">
          <PracticeCard
            icon={VideoCameraIcon}
            title="AI interview"
            description="Answer interview questions out loud or in writing. Every answer is scored, with live proctoring."
            meta="Camera and microphone"
            to="/interview"
            action="Start interview"
          />
          <PracticeCard
            icon={ClipboardDocumentCheckIcon}
            tone="secondary"
            title="Practice test"
            description="Multiple-choice questions on any topic, scored instantly with the right answers."
            meta="5–20 questions"
            to="/assessment"
            action="Start practice"
          />
        </div>
      </section>

      <section className="space-y-3" aria-labelledby="perf-heading">
        <div className="flex items-center justify-between">
          <h2 id="perf-heading" className="text-sm font-semibold text-slate-900">
            Your performance
          </h2>
          {hasPractice && <CardLink to="/reports">See details</CardLink>}
        </div>
        {!data ? (
          <StatGrid>
            {[0, 1, 2, 3].map((i) => (
              <LoadingBlock key={i} className="h-28" />
            ))}
          </StatGrid>
        ) : (
          <StatGrid>
            <StatCard label="Overall" value={formatPercent(summary.overall)} sub="Average score" icon={ChartBarIcon} />
            <StatCard label="Practice tests" value={summary.assessments} sub="Completed" icon={ClipboardDocumentCheckIcon} />
            <StatCard
              label="Interview answers"
              value={summary.interviewAnswers}
              sub={summary.interviewAverage != null ? `Avg ${formatPercent(summary.interviewAverage)}` : "Scored by AI"}
              icon={MicrophoneIcon}
            />
            <StatCard
              label="Streak"
              value={`${summary.streakDays} day${summary.streakDays === 1 ? "" : "s"}`}
              sub="Days in a row you practised"
              icon={FireIcon}
            />
          </StatGrid>
        )}
      </section>

      <Card>
        <CardHeader title="Recent results" action={hasPractice && <CardLink to="/reports">All results</CardLink>} />
        {!data ? (
          <div className="p-5">
            <LoadingBlock className="h-24" />
          </div>
        ) : !hasPractice ? (
          <EmptyState
            icon={ChartBarIcon}
            title="No results yet"
            description="Take a practice test or answer an AI interview question to see your scores here."
            action={<Button onClick={() => navigate("/assessment")}>Start a practice test</Button>}
          />
        ) : (
          <ul className="divide-y divide-slate-100">
            {data.recent.slice(0, 5).map((r) => (
              <li key={r.id} className="flex items-center gap-4 px-5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-900">{r.subject}</p>
                  <p className="text-[12px] text-slate-500">
                    {KIND_LABEL[r.kind]} · {timeAgo(r.createdAt)}
                  </p>
                </div>
                <ScoreBar value={r.score} className="hidden w-28 sm:block" />
                <span className="w-12 text-right text-sm font-semibold text-slate-900 tabular-nums">
                  {formatPercent(r.score)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {data?.improve?.length > 0 && (
        <Card className="p-5">
          <p className="text-sm font-semibold text-slate-900">Worth another look</p>
          <p className="mt-0.5 text-[13px] text-slate-500">Your lowest-scoring subjects so far.</p>
          <div className="mt-3">
            <PracticeTopicLinks subjects={data.improve} />
          </div>
        </Card>
      )}
    </div>
  );
};

export default StudentHome;
