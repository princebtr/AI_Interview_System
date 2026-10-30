import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import toast from "react-hot-toast";
import { ArrowDownTrayIcon, ChevronRightIcon, DocumentDuplicateIcon, TrashIcon } from "@heroicons/react/20/solid";
import { AcademicCapIcon, ArrowTrendingUpIcon, ChartBarIcon, CheckBadgeIcon } from "@heroicons/react/24/outline";
import api from "../../utils/axios";
import { useApi } from "../../hooks/useApi";
import { Badge, Button, Card, CardHeader, PageHeader, SlideOver } from "../../components/ui";
import { LoadError, LoadingBlock, ScoreBar, StatCard, StatGrid } from "../../components/data";
import { OptionList } from "../../components/questions";
import { AttemptBadge, TestStatusBadge } from "../../components/tests";
import { MonitoringReport, MonitoringSettings, MonitoringSummary, ViolationBadges } from "../../components/proctoring";
import { LIMIT_REASONS, monitoringFormValues, reasonLabel } from "../../utils/proctoring";
import { downloadFile, fileSlug, resultsCsv } from "../../utils/exports";
import { apiError, initials } from "../../utils/helpers";
import { formatPercent } from "../../utils/scores";
import { formatClockTime, formatDateTime, formatDuration, timeAgo } from "../../utils/time";

const FLAGS = {
  too_easy: { tone: "info", label: "Very easy", hint: "90% or more answered it correctly" },
  too_hard: { tone: "warning", label: "Very hard", hint: "30% or fewer answered it correctly" },
  check_key: {
    tone: "danger",
    label: "Check answer key",
    hint: "A wrong option was picked more often than the correct one: the question may be ambiguous or its key wrong",
  },
};

/** How each question went: % correct, which options were picked, and questions worth a second look. */
const QuestionAnalysis = ({ questions, stats }) => {
  const flagged = questions.filter((q) => stats?.[q.id]?.flag).length;
  return (
    <Card>
      <CardHeader
        title="Question analysis"
        description={`From submitted tests.${flagged ? ` ${flagged} question${flagged === 1 ? "" : "s"} worth a second look.` : ""} Questions are flagged once 5 or more students answer them.`}
      />
      <ol className="divide-y divide-slate-100">
        {questions.map((q, i) => {
          const st = stats?.[q.id];
          const flag = FLAGS[st?.flag];
          return (
            <li key={q.id} className="grid gap-3 px-5 py-3.5 sm:grid-cols-[minmax(0,1fr)_220px] sm:items-center">
              <div className="min-w-0">
                <p className="truncate text-sm text-slate-900" title={q.text}>
                  <span className="mr-1.5 text-slate-400 tabular-nums">{i + 1}.</span>
                  {q.text}
                </p>
                <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-slate-500">
                  {Object.entries(st?.picks ?? {}).map(([letter, n]) => (
                    <span key={letter} className={letter === q.correctAnswer ? "font-semibold text-emerald-700" : undefined}>
                      {letter}: {n}
                      {letter === q.correctAnswer && " ✓"}
                    </span>
                  ))}
                  {st?.skipped > 0 && <span>Skipped: {st.skipped}</span>}
                  {flag && (
                    <span title={flag.hint}>
                      <Badge tone={flag.tone}>{flag.label}</Badge>
                    </span>
                  )}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <ScoreBar value={st?.percentCorrect} className="flex-1" />
                <span className="w-24 text-right text-[13px] font-medium text-slate-700 tabular-nums">
                  {st?.percentCorrect == null ? "No answers" : `${Math.round(st.percentCorrect)}% correct`}
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
};

const AssessmentDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data, error, reload } = useApi(`/assessments/${id}`);
  const [showQuestions, setShowQuestions] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // Monitoring: one student's report, and editing the rules before anyone starts.
  const [reportFor, setReportFor] = useState(null); // student id
  const [events, setEvents] = useState(null);
  const [reviewing, setReviewing] = useState(null);
  const [rulesDraft, setRulesDraft] = useState(null);
  const [savingRules, setSavingRules] = useState(false);
  const capabilities = useApi(rulesDraft ? "/proctoring/capabilities" : null);

  // Follow results without a manual refresh while the test is running (or about to start).
  const status = data?.assessment.status;
  const startsAt = data?.assessment.startsAt;
  useEffect(() => {
    const opensSoon = status === "scheduled" && new Date(startsAt).getTime() - Date.now() < 10 * 60_000;
    if (status !== "live" && !opensSoon) return undefined;
    const timer = setInterval(reload, 15_000);
    return () => clearInterval(timer);
  }, [status, startsAt, reload]);

  if (error && !data) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Tests" title={error.response?.status === 404 ? "Test not found" : "Test"} />
        {error.response?.status === 404 ? (
          <Card className="p-6 text-center text-sm text-slate-600">
            This test doesn't exist or you can't see it.{" "}
            <Link to="/assessments" className="font-medium text-accent-700">Back to tests</Link>
          </Card>
        ) : (
          <LoadError onRetry={reload} />
        )}
      </div>
    );
  }

  const test = data?.assessment;
  const stats = data?.stats;
  const anyStarted = (data?.results ?? []).some((r) => r.status !== "not_started" && r.status !== "missed");

  const monitored = Boolean(test?.monitoring?.enabled);
  const reportRow = data?.results.find((r) => r.student.id === reportFor);

  const openReport = async (row) => {
    setReportFor(row.student.id);
    setEvents(null);
    try {
      const { data: body } = await api.get(`/assessments/${id}/violations`, { params: { student: row.student.id } });
      setEvents(body.events);
    } catch (err) {
      toast.error(apiError(err, "Couldn't load the proctoring report."));
      setEvents([]);
    }
  };

  const review = async (event, reviewStatus) => {
    setReviewing(`${event.id}:${reviewStatus}`);
    try {
      const { data: body } = await api.patch(`/assessments/${id}/violations/${event.id}`, { reviewStatus });
      setEvents((list) => list.map((e) => (e.id === event.id ? { ...e, ...body.event } : e)));
      toast.success(reviewStatus === "dismissed" ? "Violation dismissed" : "Violation upheld");
      reload();
    } catch (err) {
      toast.error(apiError(err, "Couldn't save the review."));
    } finally {
      setReviewing(null);
    }
  };

  const saveRules = async () => {
    setSavingRules(true);
    try {
      await api.patch(`/assessments/${id}`, { monitoring: rulesDraft });
      toast.success("Proctoring rules saved");
      setRulesDraft(null);
      reload();
    } catch (err) {
      const fieldError = err.response?.data?.errors?.[0]?.message;
      toast.error(fieldError ?? apiError(err, "Couldn't save the rules."));
    } finally {
      setSavingRules(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(`Delete "${test.title}"? Students in ${test.audience.label} will no longer see it.`)) return;
    setDeleting(true);
    try {
      await api.delete(`/assessments/${id}`);
      toast.success("Test deleted");
      navigate("/assessments");
    } catch (err) {
      toast.error(apiError(err, "Couldn't delete the test."));
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-[13px] text-slate-500">
        <Link to="/assessments" className="hover:text-slate-800">Tests</Link>
        <ChevronRightIcon className="size-4 text-slate-300" />
        <span className="truncate font-medium text-slate-800">{test?.title ?? "…"}</span>
      </nav>

      <PageHeader
        title={test?.title ?? "Test"}
        description={
          test &&
          `${test.audience.label} · ${formatDateTime(test.startsAt)} to ${formatClockTime(test.endsAt)} (${formatDuration(test.durationMinutes)}) · ${test.questionCount} questions × ${test.marksPerQuestion} marks = ${test.totalMarks}`
        }
        actions={
          test && (
            <>
              <TestStatusBadge status={test.status} />
              <Button variant="secondary" size="sm" onClick={() => navigate(`/assessments/new?from=${id}`)}>
                <DocumentDuplicateIcon className="size-4" />
                Duplicate
              </Button>
              {anyStarted && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    downloadFile(`${fileSlug(test.title)}-results.csv`, resultsCsv(test, data.results), "text/csv;charset=utf-8")
                  }
                >
                  <ArrowDownTrayIcon className="size-4" />
                  Export CSV
                </Button>
              )}
              {!anyStarted && (
                <Button variant="danger" size="sm" onClick={remove} loading={deleting}>
                  {!deleting && <TrashIcon className="size-4" />}
                  Delete
                </Button>
              )}
            </>
          )
        }
      />

      {stats ? (
        <StatGrid>
          <StatCard label="Students" value={stats.students} sub={test.audience.label} icon={AcademicCapIcon} />
          <StatCard label="Submitted" value={`${stats.submitted} / ${stats.students}`} sub={stats.inProgress ? `${stats.inProgress} in progress` : "Finished or auto-submitted"} icon={CheckBadgeIcon} />
          <StatCard label="Average" value={formatPercent(stats.averagePercentage)} sub="Of submitted tests" icon={ChartBarIcon} />
          <StatCard
            label="Range"
            value={stats.highestPercentage == null ? "—" : `${Math.round(stats.lowestPercentage)}–${Math.round(stats.highestPercentage)}%`}
            sub="Lowest to highest"
            icon={ArrowTrendingUpIcon}
          />
        </StatGrid>
      ) : (
        <StatGrid>
          {[0, 1, 2, 3].map((i) => <LoadingBlock key={i} className="h-28" />)}
        </StatGrid>
      )}

      <Card>
        <CardHeader title="Results" description={test?.status === "scheduled" ? "Results appear here once students start." : "Every student the test is assigned to"} />
        {!data ? (
          <div className="p-5"><LoadingBlock className="h-32" /></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-[12px] text-slate-500">
                  <th className="px-5 py-2.5 font-medium">Student</th>
                  <th className="px-5 py-2.5 font-medium">Status</th>
                  <th className="px-5 py-2.5 font-medium">Score</th>
                  {monitored && <th className="px-5 py-2.5 font-medium">Proctoring</th>}
                  <th className="hidden px-5 py-2.5 text-right font-medium md:table-cell">Submitted</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.results.length === 0 ? (
                  <tr><td colSpan={monitored ? 5 : 4} className="px-5 py-8 text-center text-[13px] text-slate-500">No students in this group yet.</td></tr>
                ) : (
                  data.results.map((r) => (
                    <tr key={r.student.id}>
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-3">
                          <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[11px] font-semibold text-slate-600">{initials(r.student.name)}</span>
                          <div className="min-w-0">
                            <p className="truncate font-medium text-slate-900">{r.student.name}</p>
                            <p className="truncate text-[13px] text-slate-500">{r.student.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-3">
                        {LIMIT_REASONS.has(r.submissionReason) ? (
                          <Badge tone="danger">{reasonLabel(r.submissionReason)}</Badge>
                        ) : (
                          <AttemptBadge status={r.status} auto={r.autoSubmitted} />
                        )}
                      </td>
                      <td className="px-5 py-3">
                        {r.score == null ? (
                          <span className="text-slate-400">{r.status === "in_progress" ? `${r.answered} answered` : "—"}</span>
                        ) : (
                          <div className="flex items-center gap-3">
                            <span className="w-16 font-medium text-slate-900 tabular-nums">{r.score} / {test.totalMarks}</span>
                            <ScoreBar value={r.percentage} className="hidden w-24 sm:block" />
                            <span className="w-10 text-right text-slate-600 tabular-nums">{formatPercent(r.percentage)}</span>
                            {r.totalPenalty > 0 && (
                              <span className="text-[12px] font-medium text-red-700 tabular-nums" title="Marks deducted for camera violations">
                                −{r.totalPenalty}
                              </span>
                            )}
                          </div>
                        )}
                      </td>
                      {monitored && (
                        <td className="px-5 py-3">
                          <div className="flex items-center gap-2">
                            <ViolationBadges counts={r.violations} />
                            {r.status !== "not_started" && r.status !== "missed" && (
                              <Button variant="ghost" size="sm" onClick={() => openReport(r)}>
                                Report
                              </Button>
                            )}
                          </div>
                        </td>
                      )}
                      <td className="hidden px-5 py-3 text-right text-slate-500 md:table-cell">{r.submittedAt ? timeAgo(r.submittedAt) : "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {test && (
        <Card>
          <CardHeader
            title="Proctoring"
            description={<MonitoringSummary monitoring={test.monitoring} />}
            action={
              !anyStarted && (
                <Button variant="secondary" size="sm" onClick={() => setRulesDraft(monitoringFormValues(test.monitoring))}>
                  Edit rules
                </Button>
              )
            }
          />
          {monitored && (
            <p className="px-5 py-3 text-[13px] leading-relaxed text-slate-500">
              Flags come from automated checks and can be wrong. Open a student's report to see the timeline, and
              uphold or dismiss each violation. Dismissing a camera violation refunds its marks.
            </p>
          )}
        </Card>
      )}

      <SlideOver
        open={Boolean(reportFor)}
        onClose={() => setReportFor(null)}
        title={reportRow ? `${reportRow.student.name}: proctoring report` : "Proctoring report"}
        description={test?.title}
      >
        {reportRow && test && (
          <MonitoringReport
            result={reportRow}
            monitoring={test.monitoring}
            totalMarks={test.totalMarks}
            events={events}
            reviewing={reviewing}
            onReview={review}
          />
        )}
      </SlideOver>

      <SlideOver
        open={Boolean(rulesDraft)}
        onClose={() => setRulesDraft(null)}
        title="Proctoring rules"
        description="Changes apply until the first student starts."
        footer={
          <>
            <Button variant="secondary" onClick={() => setRulesDraft(null)}>
              Cancel
            </Button>
            <Button onClick={saveRules} loading={savingRules}>
              Save rules
            </Button>
          </>
        }
      >
        {rulesDraft && (
          <div className="p-5">
            <MonitoringSettings value={rulesDraft} onChange={setRulesDraft} capabilities={capabilities.data} />
          </div>
        )}
      </SlideOver>

      {test && stats?.submitted > 0 && <QuestionAnalysis questions={test.questions} stats={data.questionStats} />}

      {test && (
        <Card>
          <CardHeader
            title="Questions"
            description={`${test.questionCount} questions with answer keys${test.shuffleQuestions ? ", shown to each student in a different order" : ""}`}
            action={
              <Button variant="secondary" size="sm" onClick={() => setShowQuestions((s) => !s)} aria-expanded={showQuestions}>
                {showQuestions ? "Hide" : "Show"}
              </Button>
            }
          />
          {showQuestions && (
            <ol className="divide-y divide-slate-100">
              {test.questions.map((q, i) => (
                <li key={q.id} className="px-5 py-4">
                  <p className="text-sm font-medium text-slate-900">
                    <span className="mr-1.5 text-slate-400 tabular-nums">{i + 1}.</span>
                    {q.text}
                  </p>
                  <div className="mt-3"><OptionList options={q.options} correct={q.correctAnswer} /></div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      )}
    </div>
  );
};

export default AssessmentDetail;
