import { Link, useNavigate, useParams } from "react-router-dom";
import { ChevronRightIcon, UserPlusIcon } from "@heroicons/react/20/solid";
import { AcademicCapIcon, BoltIcon, CheckBadgeIcon, ChartBarIcon } from "@heroicons/react/24/outline";
import { useApi } from "../../hooks/useApi";
import { Button, Card, CardHeader, PageHeader } from "../../components/ui";
import StudentsTable from "../../components/StudentsTable";
import { LoadError, LoadingBlock, ScoreBar, StatCard, StatGrid } from "../../components/data";
import { formatPercent } from "../../utils/scores";
import { LEVEL_META, childLevel } from "../../utils/structure";

/** One batch, department, section or cohort: its stats, its sub-groups and its students. */
const GroupDetail = () => {
  const { level, id } = useParams();
  const navigate = useNavigate();
  const meta = LEVEL_META[level] ?? { label: "Group", plural: "Groups" };
  const { data, error, reload } = useApi(LEVEL_META[level] ? `/institution/structure/${level}/${id}` : null);

  if (!LEVEL_META[level] || (error && !data)) {
    const missing = !LEVEL_META[level] || error.response?.status === 404;
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Academics" title={missing ? `${meta.label} not found` : meta.label} />
        {missing ? (
          <Card className="p-6 text-center">
            <p className="text-sm text-slate-600">This {meta.label.toLowerCase()} doesn't exist or was deleted.</p>
            <Link to="/structure" className="mt-2 inline-block text-[13px] font-medium text-accent-700">
              Back to the academic structure
            </Link>
          </Card>
        ) : (
          <LoadError onRetry={reload} />
        )}
      </div>
    );
  }

  const node = data?.node;
  const child = childLevel(level);

  return (
    <div className="space-y-6">
      <nav aria-label="Group path" className="flex flex-wrap items-center gap-1 text-[13px] text-slate-500">
        <Link to="/structure" className="hover:text-slate-800">
          Structure
        </Link>
        {(node?.path ?? []).map((p, i, all) => (
          <span key={p.id} className="flex items-center gap-1">
            <ChevronRightIcon className="size-4 text-slate-300" />
            {i === all.length - 1 ? (
              <span className="font-medium text-slate-800">{p.name}</span>
            ) : (
              <Link to={`/structure/${p.level}/${p.id}`} className="hover:text-slate-800">
                {p.name}
              </Link>
            )}
          </span>
        ))}
      </nav>

      <PageHeader
        eyebrow={meta.label}
        title={node?.name ?? meta.label}
        description={`Students in this ${meta.label.toLowerCase()} and how they're practising.`}
        actions={
          level === "cohort" && (
            <Button onClick={() => navigate(`/users?add=student&cohort=${id}`)}>
              <UserPlusIcon className="size-4" />
              Add student
            </Button>
          )
        }
      />

      {node ? (
        <StatGrid>
          <StatCard label="Students" value={node.studentCount} icon={AcademicCapIcon} />
          <StatCard
            label="Signed in"
            value={`${node.activated} / ${node.studentCount}`}
            sub="Have used their account"
            icon={CheckBadgeIcon}
          />
          <StatCard
            label="Avg practice score"
            value={formatPercent(node.averageScore)}
            sub="Last 90 days"
            icon={ChartBarIcon}
          />
          <StatCard label="Practice sessions" value={node.practice30Days} sub="Last 30 days" icon={BoltIcon} />
        </StatGrid>
      ) : (
        <StatGrid>
          {[0, 1, 2, 3].map((i) => (
            <LoadingBlock key={i} className="h-28" />
          ))}
        </StatGrid>
      )}

      {child && node && (
        <Card>
          <CardHeader
            title={LEVEL_META[child].plural}
            description={`The ${LEVEL_META[child].plural.toLowerCase()} in ${node.name}. Add or rename them from the structure page.`}
          />
          {node.children.length === 0 ? (
            <p className="px-5 py-6 text-center text-[13px] text-slate-500">
              No {LEVEL_META[child].plural.toLowerCase()} yet.{" "}
              <Link to="/structure" className="font-medium text-accent-700 hover:text-accent-800">
                Add one
              </Link>
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {node.children.map((c) => (
                <li key={c.id}>
                  <Link
                    to={`/structure/${c.level}/${c.id}`}
                    className="flex items-center gap-4 px-5 py-3 transition-colors hover:bg-slate-50"
                  >
                    <span className="min-w-0 flex-1 truncate font-medium text-slate-900">{c.name}</span>
                    <span className="text-[13px] text-slate-500 tabular-nums">
                      {c.studentCount} student{c.studentCount === 1 ? "" : "s"}
                    </span>
                    <ScoreBar value={c.averageScore} className="hidden w-24 sm:block" />
                    <span className="hidden w-10 text-right text-[13px] text-slate-700 tabular-nums sm:block">
                      {formatPercent(c.averageScore)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <Card>
        <CardHeader title="Students" description="Sorted by name. Practice stats cover the last 90 days." />
        <StudentsTable scope={{ [level]: id }} showPlacement={level !== "cohort"} />
      </Card>
    </div>
  );
};

export default GroupDetail;
