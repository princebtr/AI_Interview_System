import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ChevronRightIcon } from "@heroicons/react/20/solid";
import {
  ChartBarIcon,
  ClipboardDocumentCheckIcon,
  ClipboardDocumentListIcon,
  FireIcon,
  MicrophoneIcon,
} from "@heroicons/react/24/outline";
import { useApi } from "../../hooks/useApi";
import { Badge, Button, Card, CardHeader, PageHeader } from "../../components/ui";
import { EmptyState, LoadError, LoadingBlock, StatCard, StatGrid } from "../../components/data";
import { ChartCard, DataTable, HBarChart, Legend } from "../../components/charts";
import { RangeFilter, ScoreTrendCard, SubjectsCard, WeeklyCountCard } from "../../components/reports";
import { SINGLE, dateLabel } from "../../utils/reports";
import { PracticeTopicLinks } from "../../components/tests";
import { formatPercent } from "../../utils/scores";
import { timeAgo } from "../../utils/time";

const KIND_LABEL = { mcq: "Practice test", interview: "AI interview" };
const STATUS = {
  submitted: null,
  missed: { label: "Missed", tone: "danger" },
  open: { label: "Open now", tone: "info" },
};

/** "vs 64% in your cohort" style comparison, or the fallback. */
const versus = (value, group, who, fallback) =>
  value !== null && group !== null ? `${who} average ${formatPercent(group)}` : fallback;

/**
 * One student's report. Students see their own (/reports); admins and educators
 * open any student's from the class report or a student list (/reports/students/:id).
 */
const StudentReport = () => {
  const { id } = useParams();
  const staff = Boolean(id);
  const navigate = useNavigate();
  const [days, setDays] = useState(90);
  const { data, error, loading, reload } = useApi(staff ? `/reports/students/${id}` : "/reports/me", { days });

  const student = data?.student;
  const header = (
    <>
      {staff && (
        <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-[13px] text-slate-500">
          <Link to="/reports" className="hover:text-slate-800">
            Reports
          </Link>
          <ChevronRightIcon className="size-4 text-slate-300" />
          <span className="font-medium text-slate-800">{student?.name ?? "Student"}</span>
        </nav>
      )}
      <PageHeader
        eyebrow={staff ? "Student report" : "You"}
        title={staff ? (student?.name ?? "Student") : "My reports"}
        description={
          staff
            ? [student?.placement?.label, student?.email].filter(Boolean).join(" · ")
            : "How your practice, AI interviews and scheduled tests are going."
        }
      />
    </>
  );

  if (error && !data) {
    const missing = error.response?.status === 404;
    return (
      <div className="space-y-6">
        {header}
        {missing ? (
          <Card className="p-6 text-center text-sm text-slate-600">This student doesn't exist or was removed.</Card>
        ) : (
          <LoadError onRetry={reload} />
        )}
      </div>
    );
  }

  const filters = (
    <div className="flex flex-wrap items-center gap-3">
      <RangeFilter value={days} onChange={setDays} />
    </div>
  );

  if (!data) {
    return (
      <div className="space-y-6">
        {header}
        {filters}
        <StatGrid>
          {[0, 1, 2, 3].map((i) => (
            <LoadingBlock key={i} className="h-28" />
          ))}
        </StatGrid>
        <LoadingBlock className="h-72" />
      </div>
    );
  }

  const { summary, trend, subjects, tests, recent } = data;
  const busy = loading;
  const nothing = summary.practiceTests + summary.interviewAnswers + summary.testsTaken + summary.testsMissed === 0;
  const improve = subjects.filter((s) => s.averageScore !== null && s.averageScore < 70).slice(0, 3);
  const cohortWho = staff ? "Cohort" : "Your cohort";

  return (
    <div className="space-y-6">
      {header}
      {filters}

      <StatGrid>
        <StatCard
          label="Practice tests"
          value={formatPercent(summary.practiceAverage)}
          sub={versus(
            summary.practiceAverage,
            summary.cohortPracticeAverage,
            cohortWho,
            `${summary.practiceTests} taken`
          )}
          icon={ClipboardDocumentCheckIcon}
        />
        <StatCard
          label="AI interview"
          value={formatPercent(summary.interviewAverage)}
          sub={`${summary.interviewAnswers} answer${summary.interviewAnswers === 1 ? "" : "s"} scored`}
          icon={MicrophoneIcon}
        />
        <StatCard
          label="Scheduled tests"
          value={formatPercent(summary.testAverage)}
          sub={`${summary.testsTaken} taken${summary.testsMissed ? ` · ${summary.testsMissed} missed` : ""}`}
          icon={ClipboardDocumentListIcon}
        />
        <StatCard
          label="Practice streak"
          value={`${summary.streakDays} day${summary.streakDays === 1 ? "" : "s"}`}
          sub={summary.streakDays ? "Keep it going" : "Practise today to start one"}
          icon={FireIcon}
        />
      </StatGrid>

      {nothing ? (
        <Card>
          <EmptyState
            icon={ChartBarIcon}
            title="Nothing in this period"
            description={
              staff
                ? "This student hasn't practised or taken a scheduled test in this period. Try a longer range."
                : "Your charts fill in after your first practice test, AI interview answer or scheduled test."
            }
            action={
              !staff && <Button onClick={() => navigate("/assessment")}>Start a practice test</Button>
            }
          />
        </Card>
      ) : (
        <>
          <ScoreTrendCard trend={trend} busy={busy} />

          <div className="grid gap-6 lg:grid-cols-2">
            <WeeklyCountCard
              title="Practice activity"
              description="Practice tests and AI interview answers per week"
              trend={trend}
              yKey="sessions"
              yLabel="sessions"
              busy={busy}
            />
            <SubjectsCard subjects={subjects} busy={busy} />
          </div>

          <ChartCard
            title="Scheduled tests"
            description="Score in each test, newest first"
            busy={busy}
            legend={
              tests.some((t) => t.groupAverage !== null) && (
                <Legend
                  mark="rect"
                  items={[
                    { label: staff ? "Student's score" : "Your score", color: SINGLE },
                    { label: "Average of everyone who took it", mark: "tick" },
                  ]}
                />
              )
            }
            table={
              <DataTable
                caption="Scheduled test results"
                columns={[
                  { key: "title", label: "Test" },
                  { key: "startsAt", label: "Date", format: dateLabel },
                  {
                    key: "percentage",
                    label: "Score",
                    align: "right",
                    format: (v, row) => (row.status === "submitted" ? formatPercent(v) : STATUS[row.status].label),
                  },
                  { key: "groupAverage", label: "Average of everyone", align: "right", format: formatPercent },
                ]}
                rows={tests}
              />
            }
          >
            <HBarChart
              items={tests.map((t) => ({
                key: t.id,
                label: t.title,
                sub: dateLabel(t.startsAt),
                value: t.status === "submitted" ? t.percentage : null,
                emptyValue: STATUS[t.status]?.label,
                marker: t.groupAverage,
              }))}
              format={formatPercent}
              markerLabel="Average of everyone who took it"
              empty="No scheduled tests in this period."
            />
          </ChartCard>

          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <Card>
              <CardHeader title="Recent practice" description="The latest scored sessions" />
              {recent.length === 0 ? (
                <p className="px-5 py-8 text-center text-[13px] text-slate-500">No practice in this period.</p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {recent.map((a) => (
                    <li key={a.id} className="flex items-center gap-3 px-5 py-2.5">
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm text-slate-900">{a.subject}</span>
                        <span className="text-[12px] text-slate-500">
                          {KIND_LABEL[a.kind]} · {timeAgo(a.createdAt)}
                        </span>
                      </span>
                      <span className="text-sm font-semibold text-slate-900 tabular-nums">{formatPercent(a.score)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <CardHeader
                title={staff ? "Needs work" : "Where to improve"}
                description="Subjects averaging under 70%"
              />
              <div className="p-5">
                {improve.length === 0 ? (
                  <p className="text-[13px] text-slate-500">
                    {subjects.length ? "Every subject is at 70% or above. Nice." : "No practice in this period."}
                  </p>
                ) : (
                  <div className="space-y-3">
                    {/* Students get a one-click practice link per subject; staff just the list. */}
                    {staff ? (
                      <ul className="flex flex-wrap gap-2">
                        {improve.map((s) => (
                          <li key={s.subject}>
                            <Badge tone="warning">
                              {s.subject} · {formatPercent(s.averageScore)}
                            </Badge>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <>
                        <p className="text-[13px] text-slate-600">
                          {improve.map((s) => `${s.subject} (${formatPercent(s.averageScore)})`).join(", ")}. A
                          practice test on each is one click away:
                        </p>
                        <PracticeTopicLinks subjects={improve.map((s) => s.subject)} />
                      </>
                    )}
                  </div>
                )}
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
};

export default StudentReport;
