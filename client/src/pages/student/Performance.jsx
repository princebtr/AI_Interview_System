import { useNavigate } from "react-router-dom";
import { ChartBarIcon, ClipboardDocumentCheckIcon, FireIcon, MicrophoneIcon } from "@heroicons/react/24/outline";
import { useApi } from "../../hooks/useApi";
import { Badge, Button, Card, CardHeader, PageHeader } from "../../components/ui";
import { BarList, EmptyState, LoadError, LoadingBlock, ScoreBar, StatCard, StatGrid } from "../../components/data";
import { PracticeTopicLinks } from "../../components/tests";
import { formatPercent } from "../../utils/scores";
import { timeAgo } from "../../utils/time";

const KIND_LABEL = { mcq: "Practice test", interview: "AI interview" };

const Performance = () => {
  const navigate = useNavigate();
  const { data, error, reload } = useApi("/me/performance");

  const header = (
    <PageHeader
      eyebrow="You"
      title="My performance"
      description="Based on your practice tests and AI interview answers."
    />
  );

  if (error && !data) {
    return (
      <div className="space-y-8">
        {header}
        <LoadError onRetry={reload} />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-8">
        {header}
        <StatGrid>
          {[0, 1, 2, 3].map((i) => (
            <LoadingBlock key={i} className="h-28" />
          ))}
        </StatGrid>
        <LoadingBlock className="h-64" />
      </div>
    );
  }

  const { summary, subjects, improve, recent } = data;

  if (summary.attempts === 0) {
    return (
      <div className="space-y-8">
        {header}
        <Card>
          <EmptyState
            icon={ChartBarIcon}
            title="Nothing to show yet"
            description="Your scores appear here after your first practice test or AI interview answer."
            action={
              <>
                <Button onClick={() => navigate("/assessment")}>Start a practice test</Button>
                <Button variant="secondary" onClick={() => navigate("/interview")}>
                  Try an AI interview
                </Button>
              </>
            }
          />
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {header}

      <StatGrid>
        <StatCard label="Overall" value={formatPercent(summary.overall)} sub={`Across ${summary.attempts} results`} icon={ChartBarIcon} />
        <StatCard label="Practice tests" value={summary.assessments} sub="Completed" icon={ClipboardDocumentCheckIcon} />
        <StatCard
          label="AI interview"
          value={formatPercent(summary.interviewAverage)}
          sub={`${summary.interviewAnswers} answer${summary.interviewAnswers === 1 ? "" : "s"} scored`}
          icon={MicrophoneIcon}
        />
        <StatCard
          label="Streak"
          value={`${summary.streakDays} day${summary.streakDays === 1 ? "" : "s"}`}
          sub="Days in a row you practised"
          icon={FireIcon}
        />
      </StatGrid>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="By subject" description="Your average score in each subject" />
          <div className="p-5">
            <BarList
              items={subjects.map((s) => ({
                key: s.subject,
                label: s.subject,
                value: s.averageScore,
                meta: `${s.attempts} result${s.attempts === 1 ? "" : "s"}`,
              }))}
            />
          </div>
        </Card>
        <Card>
          <CardHeader title="Areas to improve" description="Subjects where your average is below 70%" />
          <div className="p-5">
            {improve.length ? (
              <PracticeTopicLinks subjects={improve} />
            ) : (
              <p className="text-[13px] leading-relaxed text-slate-500">
                Nothing below 70% right now. Try a harder subject to keep stretching yourself.
              </p>
            )}
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="History" description="Your latest results, newest first" />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-[12px] text-slate-500">
                <th className="px-5 py-2.5 font-medium">Subject</th>
                <th className="hidden px-5 py-2.5 font-medium sm:table-cell">Type</th>
                <th className="hidden px-5 py-2.5 font-medium md:table-cell">When</th>
                <th className="px-5 py-2.5 font-medium">Score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {recent.map((r) => (
                <tr key={r.id}>
                  <td className="px-5 py-3 font-medium text-slate-900">{r.subject}</td>
                  <td className="hidden px-5 py-3 text-slate-600 sm:table-cell">
                    {KIND_LABEL[r.kind]}
                    {r.kind === "mcq" && r.total ? ` · ${r.correct}/${r.total}` : ""}
                  </td>
                  <td className="hidden px-5 py-3 text-slate-500 md:table-cell">{timeAgo(r.createdAt)}</td>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-3">
                      <ScoreBar value={r.score} className="w-20 sm:w-32" />
                      <span className="w-10 text-right font-medium text-slate-900 tabular-nums">
                        {formatPercent(r.score)}
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};

export default Performance;
