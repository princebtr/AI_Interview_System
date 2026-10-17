import { Link, useNavigate, useParams } from "react-router-dom";
import { ChevronRightIcon, UserPlusIcon } from "@heroicons/react/20/solid";
import { AcademicCapIcon, BoltIcon, CheckBadgeIcon, ChartBarIcon } from "@heroicons/react/24/outline";
import { useApi } from "../../hooks/useApi";
import { Button, Card, CardHeader, PageHeader } from "../../components/ui";
import StudentsTable from "../../components/StudentsTable";
import { LoadError, LoadingBlock, StatCard, StatGrid } from "../../components/data";
import { formatPercent } from "../../utils/scores";

const CohortDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data, error, reload } = useApi(`/institution/cohorts/${id}`);

  if (error && !data) {
    const missing = error.response?.status === 404;
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Academics" title={missing ? "Cohort not found" : "Cohort"} />
        {missing ? (
          <Card className="p-6 text-center">
            <p className="text-sm text-slate-600">This cohort doesn't exist or was deleted.</p>
            <Link to="/cohorts" className="mt-2 inline-block text-[13px] font-medium text-accent-700">
              Back to cohorts
            </Link>
          </Card>
        ) : (
          <LoadError onRetry={reload} />
        )}
      </div>
    );
  }

  const cohort = data?.cohort;

  return (
    <div className="space-y-6">
      <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-[13px] text-slate-500">
        <Link to="/cohorts" className="hover:text-slate-800">
          Cohorts
        </Link>
        <ChevronRightIcon className="size-4 text-slate-300" />
        <span className="font-medium text-slate-800">{cohort?.name ?? "…"}</span>
      </nav>

      <PageHeader
        title={cohort?.name ?? "Cohort"}
        description="Students in this cohort and how they're practising."
        actions={
          <Button onClick={() => navigate(`/users?add=student&cohort=${id}`)}>
            <UserPlusIcon className="size-4" />
            Add student
          </Button>
        }
      />

      {cohort ? (
        <StatGrid>
          <StatCard label="Students" value={cohort.studentCount} icon={AcademicCapIcon} />
          <StatCard
            label="Signed in"
            value={`${cohort.activated} / ${cohort.studentCount}`}
            sub="Have used their account"
            icon={CheckBadgeIcon}
          />
          <StatCard
            label="Avg practice score"
            value={formatPercent(cohort.averageScore)}
            sub="Last 90 days"
            icon={ChartBarIcon}
          />
          <StatCard
            label="Practice sessions"
            value={cohort.practice30Days}
            sub="Last 30 days"
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

      <Card>
        <CardHeader title="Students" description="Sorted by name. Practice stats cover the last 90 days." />
        <StudentsTable cohortId={id} showCohort={false} />
      </Card>
    </div>
  );
};

export default CohortDetail;
