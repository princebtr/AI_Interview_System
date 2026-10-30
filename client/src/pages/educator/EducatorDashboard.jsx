import { Link, useNavigate } from "react-router-dom";
import { PlusIcon } from "@heroicons/react/20/solid";
import {
  AcademicCapIcon,
  BoltIcon,
  ClipboardDocumentListIcon,
  RectangleStackIcon,
  SparklesIcon,
} from "@heroicons/react/24/outline";
import { useAuth } from "../../context/AuthContext";
import { useApi } from "../../hooks/useApi";
import { useServerClock } from "../../hooks/useServerClock";
import { Button, Card, CardHeader, GlowBackdrop, PageHeader } from "../../components/ui";
import { AiBadge, DifficultyBadge } from "../../components/questions";
import { TestStatusBadge } from "../../components/tests";
import {
  BarList,
  CardLink,
  EmptyState,
  LoadError,
  LoadingBlock,
  ScoreBar,
  StatCard,
  StatGrid,
} from "../../components/data";
import { formatPercent } from "../../utils/scores";
import { firstName, greeting, timeAgo, timeUntil, todayLabel } from "../../utils/time";

// Its own component so the once-a-second clock only re-renders this card.
const UpcomingTests = () => {
  const navigate = useNavigate();
  const { data, error, reload } = useApi("/assessments");
  const now = useServerClock(data?.serverTime);
  const upcoming = (data?.assessments ?? [])
    .filter((t) => new Date(t.endsAt).getTime() > now)
    .sort((a, b) => new Date(a.startsAt) - new Date(b.startsAt))
    .slice(0, 4);

  return (
    <Card>
      <CardHeader title="Upcoming tests" action={<CardLink to="/assessments">All tests</CardLink>} />
      {error && !data ? (
        <div className="p-5">
          <LoadError onRetry={reload} />
        </div>
      ) : !data ? (
        <div className="space-y-3 p-5">
          {[0, 1].map((i) => (
            <LoadingBlock key={i} className="h-12" />
          ))}
        </div>
      ) : upcoming.length === 0 ? (
        <EmptyState
          icon={ClipboardDocumentListIcon}
          title="No upcoming tests"
          description="Schedule a timed multiple-choice test from your question bank and assign it to a batch, department, section or cohort."
          action={
            <Button onClick={() => navigate("/assessments/new")}>
              <PlusIcon className="size-4" />
              Create test
            </Button>
          }
        />
      ) : (
        <ul className="divide-y divide-slate-100">
          {upcoming.map((t) => {
            const live = new Date(t.startsAt).getTime() <= now;
            return (
              <li key={t.id}>
                <Link to={`/assessments/${t.id}`} className="block px-5 py-3.5 transition-colors hover:bg-slate-50">
                  <div className="flex items-center justify-between gap-3">
                    <p className="truncate text-sm font-medium text-slate-900">{t.title}</p>
                    <TestStatusBadge status={live ? "live" : "scheduled"} />
                  </div>
                  <p className="mt-0.5 text-[12px] text-slate-500">
                    {t.audience.label} ·{" "}
                    {live ? `${t.submitted} of ${t.students} submitted` : `opens ${timeUntil(t.startsAt, now)}`}
                  </p>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
};

const EducatorDashboard = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data, error, reload } = useApi("/teaching/overview");

  const header = (
    <PageHeader
      eyebrow={todayLabel()}
      title={
        <>
          {greeting()}, <span className="text-accent-600">{firstName(user?.name)}</span>
        </>
      }
      description="Build question sets with AI, schedule tests for any group of students and see how your students are doing."
      actions={
        <>
          <Button variant="secondary" onClick={() => navigate("/questions/add")}>
            <PlusIcon className="size-4" />
            Add questions
          </Button>
          <Button onClick={() => navigate("/assessments/new")}>
            <PlusIcon className="size-4" />
            Create test
          </Button>
        </>
      }
    />
  );

  if (error && !data) {
    return (
      <div className="relative isolate space-y-8">
        <GlowBackdrop className="-inset-x-4 -top-8 h-96 sm:-inset-x-6 lg:-inset-x-10 lg:-top-10" />
        {header}
        <LoadError onRetry={reload} />
      </div>
    );
  }

  const counts = data?.counts;

  return (
    <div className="relative isolate space-y-8">
      <GlowBackdrop className="-inset-x-4 -top-8 h-96 sm:-inset-x-6 lg:-inset-x-10 lg:-top-10" />
      {header}

      {data ? (
        <StatGrid>
          <StatCard
            label="Question bank"
            value={counts.questions}
            sub={`${counts.myQuestions} added by you`}
            icon={RectangleStackIcon}
            to="/questions"
          />
          <StatCard
            label="AI-generated"
            value={counts.aiGenerated}
            sub="Reviewed before saving"
            icon={SparklesIcon}
            to="/questions/add"
          />
          <StatCard
            label="Students"
            value={counts.students}
            sub={`${counts.sections} section${counts.sections === 1 ? "" : "s"} · ${counts.cohorts} cohort${counts.cohorts === 1 ? "" : "s"}`}
            icon={AcademicCapIcon}
            to="/students"
          />
          <StatCard
            label="Practice sessions"
            value={data.practice.last7Days}
            sub="By students, last 7 days"
            icon={BoltIcon}
          />
        </StatGrid>
      ) : (
        <StatGrid>
          {[0, 1, 2, 3].map((i) => (
            <LoadingBlock key={i} className="h-28" />
          ))}
        </StatGrid>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader
              title="Section performance"
              description="Average practice score per section, last 90 days"
              action={<CardLink to="/students">My students</CardLink>}
            />
            {!data ? (
              <div className="p-5">
                <LoadingBlock className="h-28" />
              </div>
            ) : data.sections.length === 0 ? (
              <EmptyState
                icon={AcademicCapIcon}
                title="No sections yet"
                description="Your admin sets up batches, departments, sections and cohorts, then adds students."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-[12px] text-slate-500">
                      <th className="px-5 py-2.5 font-medium">Section</th>
                      <th className="px-5 py-2.5 text-right font-medium">Students</th>
                      <th className="hidden px-5 py-2.5 text-right font-medium sm:table-cell">Sessions</th>
                      <th className="px-5 py-2.5 font-medium">Avg score</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.sections.map((c) => (
                      <tr key={c.id}>
                        <td className="px-5 py-3 font-medium text-slate-900">{c.label}</td>
                        <td className="px-5 py-3 text-right text-slate-700 tabular-nums">{c.students}</td>
                        <td className="hidden px-5 py-3 text-right text-slate-500 tabular-nums sm:table-cell">
                          {c.attempts}
                        </td>
                        <td className="px-5 py-3">
                          <div className="flex items-center gap-3">
                            <ScoreBar value={c.averageScore} className="w-24 sm:w-36" />
                            <span className="w-10 text-right text-slate-700 tabular-nums">
                              {formatPercent(c.averageScore)}
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card>
            <CardHeader
              title="Topic strengths and weaknesses"
              description="Students' average practice score by subject, last 90 days"
            />
            <div className="p-5">
              {!data ? (
                <LoadingBlock className="h-32" />
              ) : (
                <BarList
                  items={data.subjects.map((s) => ({
                    key: s.subject,
                    label: s.subject,
                    value: s.averageScore,
                    meta: `${s.attempts} session${s.attempts === 1 ? "" : "s"}`,
                  }))}
                  emptyText="Topics appear here once students start practising."
                />
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <UpcomingTests />

          <Card>
            <CardHeader
              title="Recently added questions"
              action={<CardLink to="/questions">Question bank</CardLink>}
            />
            {!data ? (
              <div className="space-y-3 p-5">
                {[0, 1, 2].map((i) => (
                  <LoadingBlock key={i} className="h-12" />
                ))}
              </div>
            ) : data.recentQuestions.length === 0 ? (
              <EmptyState
                icon={SparklesIcon}
                title="No questions yet"
                description="Generate a set with AI, write your own, or import them from a sheet."
                action={
                  <Button onClick={() => navigate("/questions/add")}>
                    <PlusIcon className="size-4" />
                    Add questions
                  </Button>
                }
              />
            ) : (
              <ul className="divide-y divide-slate-100">
                {data.recentQuestions.map((q) => (
                  <li key={q.id} className="px-5 py-3.5">
                    <p className="line-clamp-2 text-sm text-slate-900">{q.text}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[12px] text-slate-500">
                      <span className="font-medium text-slate-700">{q.subject}</span>
                      <DifficultyBadge value={q.difficulty} />
                      {q.aiGenerated && <AiBadge />}
                      <span>· {timeAgo(q.createdAt)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
};

export default EducatorDashboard;
