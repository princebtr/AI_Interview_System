import { Link, useNavigate } from "react-router-dom";
import { PlusIcon } from "@heroicons/react/20/solid";
import { ClipboardDocumentListIcon } from "@heroicons/react/24/outline";
import { useAuth } from "../../context/AuthContext";
import { useApi } from "../../hooks/useApi";
import { Button, Card, PageHeader } from "../../components/ui";
import { EmptyState, LoadError, ScoreBar } from "../../components/data";
import { TestStatusBadge } from "../../components/tests";
import { formatPercent } from "../../utils/scores";
import { formatDateTime, formatDuration } from "../../utils/time";

const Assessments = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data, error, loading, reload } = useApi("/assessments");
  const tests = data?.assessments ?? [];
  const isAdmin = user?.role === "admin";

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={isAdmin ? "Evaluation" : "Teaching"}
        title="Tests"
        description={
          isAdmin
            ? "Every scheduled test in your institution, with submissions and average scores."
            : "Schedule multiple-choice tests for your cohorts and follow the results."
        }
        actions={
          <Button onClick={() => navigate("/assessments/new")}>
            <PlusIcon className="size-4" />
            Create test
          </Button>
        }
      />

      {error && !data ? (
        <LoadError onRetry={reload} />
      ) : (
        <Card>
          {loading && !data ? (
            <div className="space-y-3 p-5">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-10 animate-pulse rounded bg-slate-100" />
              ))}
            </div>
          ) : tests.length === 0 ? (
            <EmptyState
              icon={ClipboardDocumentListIcon}
              title="No tests yet"
              description="Create a test from your question bank, pick when it happens and assign it to a cohort."
              action={
                <Button onClick={() => navigate("/assessments/new")}>
                  <PlusIcon className="size-4" />
                  Create test
                </Button>
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-[12px] text-slate-500">
                    <th className="px-5 py-2.5 font-medium">Test</th>
                    <th className="hidden px-5 py-2.5 font-medium md:table-cell">Cohort</th>
                    <th className="hidden px-5 py-2.5 font-medium lg:table-cell">When</th>
                    <th className="px-5 py-2.5 font-medium">Status</th>
                    <th className="hidden px-5 py-2.5 text-right font-medium sm:table-cell">Submitted</th>
                    <th className="hidden px-5 py-2.5 font-medium md:table-cell">Average</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {tests.map((t) => (
                    <tr key={t.id} className="transition-colors hover:bg-slate-50">
                      <td className="px-5 py-3">
                        <Link to={`/assessments/${t.id}`} className="font-medium text-slate-900 hover:text-accent-700">
                          {t.title}
                        </Link>
                        <p className="text-[12px] text-slate-500">
                          {t.questionCount} questions · {t.totalMarks} marks · {formatDuration(t.durationMinutes)}
                          {isAdmin && t.createdBy && ` · ${t.createdBy.name}`}
                        </p>
                      </td>
                      <td className="hidden px-5 py-3 text-slate-700 md:table-cell">{t.cohort.name}</td>
                      <td className="hidden px-5 py-3 text-slate-600 lg:table-cell">{formatDateTime(t.startsAt)}</td>
                      <td className="px-5 py-3">
                        <TestStatusBadge status={t.status} />
                      </td>
                      <td className="hidden px-5 py-3 text-right text-slate-700 tabular-nums sm:table-cell">
                        {t.submitted} / {t.students}
                      </td>
                      <td className="hidden px-5 py-3 md:table-cell">
                        <div className="flex items-center gap-3">
                          <ScoreBar value={t.averagePercentage} className="w-20" />
                          <span className="w-10 text-right text-slate-700 tabular-nums">{formatPercent(t.averagePercentage)}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
};

export default Assessments;
