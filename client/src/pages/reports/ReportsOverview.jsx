import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDownIcon, ChevronUpIcon } from "@heroicons/react/20/solid";
import {
  AcademicCapIcon,
  ChartBarIcon,
  ClipboardDocumentCheckIcon,
  ClipboardDocumentListIcon,
} from "@heroicons/react/24/outline";
import { useApi } from "../../hooks/useApi";
import { Card, CardHeader, PageHeader, SearchInput } from "../../components/ui";
import { EmptyState, LoadError, LoadingBlock, StatCard, StatGrid } from "../../components/data";
import { ChartCard, ColumnChart, DataTable, HBarChart } from "../../components/charts";
import GroupPicker from "../../components/GroupPicker";
import { RangeFilter, ScoreTrendCard, SubjectsCard, WeeklyCountCard } from "../../components/reports";
import { dateLabel } from "../../utils/reports";
import { cx } from "../../utils/helpers";
import { formatPercent } from "../../utils/scores";
import { timeAgo } from "../../utils/time";
import { EMPTY_SELECTION, LEVEL_META, selectionParams } from "../../utils/structure";

const COLUMNS = [
  { key: "name", label: "Student" },
  { key: "practiceAverage", label: "Practice avg", numeric: true },
  { key: "practiceSessions", label: "Sessions", numeric: true },
  { key: "testAverage", label: "Test avg", numeric: true },
  { key: "testsMissed", label: "Missed", numeric: true },
  { key: "lastActiveAt", label: "Last active", numeric: true },
];

/** Every student in scope; sortable, searchable, each linking to their own report. */
const StudentsReportTable = ({ students }) => {
  const [sort, setSort] = useState({ key: "name", dir: 1 });
  const [search, setSearch] = useState("");
  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const matching = q
      ? students.filter((s) => s.name.toLowerCase().includes(q) || s.email.toLowerCase().includes(q))
      : students;
    // Students with no value sort last whichever way the column is sorted.
    return [...matching].sort((a, b) => {
      const [x, y] = [a[sort.key], b[sort.key]];
      if (x === null || x === undefined) return y === null || y === undefined ? 0 : 1;
      if (y === null || y === undefined) return -1;
      return (typeof x === "string" ? x.localeCompare(y, undefined, { sensitivity: "base" }) : x - y) * sort.dir;
    });
  }, [students, sort, search]);

  const toggle = (key) => setSort((s) => (s.key === key ? { key, dir: -s.dir } : { key, dir: key === "name" ? 1 : -1 }));

  return (
    <Card>
      <CardHeader
        title="Students"
        description="Click a student for their own report. Sort a column to find who needs help."
        action={
          <SearchInput
            id="report-students-search"
            label="Search students"
            className="sm:w-56"
            value={search}
            placeholder="Search name or email"
            onChange={(e) => setSearch(e.target.value)}
          />
        }
      />
      <div className="max-h-[32rem] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-white">
            <tr className="border-b border-slate-100 text-left text-[12px] text-slate-500">
              {COLUMNS.map((c, i) => (
                <th
                  key={c.key}
                  aria-sort={sort.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
                  className={cx(
                    "px-5 py-2.5 font-medium",
                    c.numeric && "text-right",
                    i >= 2 && i !== 4 && "hidden md:table-cell"
                  )}
                >
                  <button
                    type="button"
                    onClick={() => toggle(c.key)}
                    className={cx("inline-flex items-center gap-1 hover:text-slate-800", sort.key === c.key && "text-slate-900")}
                  >
                    {c.label}
                    {sort.key === c.key &&
                      (sort.dir === 1 ? <ChevronUpIcon className="size-3.5" /> : <ChevronDownIcon className="size-3.5" />)}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 ? (
              <tr>
                <td colSpan={COLUMNS.length} className="px-5 py-8 text-center text-[13px] text-slate-500">
                  {students.length ? "No students match your search." : "No students in this group yet."}
                </td>
              </tr>
            ) : (
              rows.map((s) => (
                <tr key={s.id} className="transition-colors hover:bg-slate-50">
                  <td className="px-5 py-2.5">
                    <Link to={`/reports/students/${s.id}`} className="font-medium text-slate-900 hover:text-accent-700">
                      {s.name}
                    </Link>
                    <p className="truncate text-[12px] text-slate-500">{s.placement ?? s.email}</p>
                  </td>
                  <td className="px-5 py-2.5 text-right text-slate-900 tabular-nums">{formatPercent(s.practiceAverage)}</td>
                  <td className="hidden px-5 py-2.5 text-right text-slate-700 tabular-nums md:table-cell">
                    {s.practiceSessions}
                  </td>
                  <td className="hidden px-5 py-2.5 text-right text-slate-900 tabular-nums md:table-cell">
                    {formatPercent(s.testAverage)}
                  </td>
                  <td className={cx("px-5 py-2.5 text-right tabular-nums", s.testsMissed ? "font-medium text-red-700" : "text-slate-500")}>
                    {s.testsMissed}
                  </td>
                  <td className="hidden px-5 py-2.5 text-right text-[13px] text-slate-500 md:table-cell">
                    {s.lastActiveAt ? timeAgo(s.lastActiveAt) : "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
};

/** Admins and educators: how the institution, or any group in it, is doing. */
const ReportsOverview = () => {
  const [days, setDays] = useState(90);
  const [selection, setSelection] = useState(EMPTY_SELECTION);
  const structure = useApi("/institution/structure");
  const tree = structure.data?.batches ?? [];
  const { data, error, loading, reload } = useApi("/reports/overview", { days, ...selectionParams(selection) });

  // Clicking a group in the breakdown narrows the whole report to it.
  const drillInto = (group) => setSelection((prev) => ({ ...prev, [group.level]: group.id }));

  const filters = (
    <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
      <RangeFilter value={days} onChange={setDays} />
      {tree.length > 0 && (
        <GroupPicker mode="filter" idPrefix="reports" tree={tree} value={selection} onChange={setSelection} className="xl:flex-1" />
      )}
    </div>
  );

  const header = (
    <PageHeader
      eyebrow="Reports"
      title={data?.scope ? data.scope.label : "Institution report"}
      description="Practice, AI interviews and scheduled tests across your students. Filter by date range or group, or open any student's report."
    />
  );

  if (error && !data) {
    return (
      <div className="space-y-6">
        {header}
        {filters}
        <LoadError onRetry={reload} />
      </div>
    );
  }
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

  const { summary, trend, distribution, unpractised, groups, subjects, tests, students } = data;
  const busy = loading;
  const childLevel = groups[0]?.level;

  return (
    <div className="space-y-6">
      {header}
      {filters}

      <StatGrid>
        <StatCard
          label="Students"
          value={summary.students}
          sub={`${summary.activeStudents} active in this period`}
          icon={AcademicCapIcon}
        />
        <StatCard
          label="Practice average"
          value={formatPercent(summary.overallPracticeAverage)}
          sub={`${summary.practiceSessions} session${summary.practiceSessions === 1 ? "" : "s"}`}
          icon={ClipboardDocumentCheckIcon}
        />
        <StatCard
          label="Scheduled tests"
          value={formatPercent(summary.testAverage)}
          sub={`${summary.testSubmissions} submission${summary.testSubmissions === 1 ? "" : "s"}`}
          icon={ClipboardDocumentListIcon}
        />
        <StatCard
          label="Test completion"
          value={formatPercent(summary.completionRate)}
          sub={summary.testsMissed ? `${summary.testsMissed} missed` : "None missed"}
          icon={ChartBarIcon}
        />
      </StatGrid>

      {summary.students === 0 ? (
        <Card>
          <EmptyState
            icon={AcademicCapIcon}
            title="No students here yet"
            description="Reports fill in once students in this group practise or take scheduled tests."
          />
        </Card>
      ) : (
        <>
          <ScoreTrendCard trend={trend} busy={busy} description="Weekly average score across these students" />

          <div className="grid gap-6 lg:grid-cols-2">
            <WeeklyCountCard
              title="Active students"
              description="Students who practised or took a test, per week"
              trend={trend}
              yKey="activeStudents"
              yLabel="active students"
              busy={busy}
            />
            <ChartCard
              title="Score distribution"
              description={`Students by average practice score${unpractised ? ` · ${unpractised} haven't practised` : ""}`}
              busy={busy}
              table={
                <DataTable
                  caption="Students by average practice score"
                  columns={[
                    { key: "band", label: "Average score" },
                    { key: "students", label: "Students", align: "right" },
                  ]}
                  rows={distribution}
                />
              }
            >
              <ColumnChart data={distribution} xKey="band" xFormat={(b) => b} yKey="students" yLabel="students" />
            </ChartCard>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {childLevel && (
              <ChartCard
                title={`By ${LEVEL_META[childLevel].label.toLowerCase()}`}
                description="Average practice score; click one to narrow the report to it"
                busy={busy}
                table={
                  <DataTable
                    caption={`Results by ${LEVEL_META[childLevel].label.toLowerCase()}`}
                    columns={[
                      { key: "name", label: LEVEL_META[childLevel].label },
                      { key: "students", label: "Students", align: "right" },
                      { key: "activeStudents", label: "Active", align: "right" },
                      { key: "practiceAverage", label: "Practice avg", align: "right", format: formatPercent },
                      { key: "testAverage", label: "Test avg", align: "right", format: formatPercent },
                    ]}
                    rows={groups}
                  />
                }
              >
                <HBarChart
                  items={groups.map((g) => ({
                    key: g.id,
                    label: g.name,
                    sub: `${g.students} student${g.students === 1 ? "" : "s"} · tests ${formatPercent(g.testAverage)}`,
                    value: g.practiceAverage,
                    onClick: () => drillInto(g),
                  }))}
                  format={formatPercent}
                />
              </ChartCard>
            )}
            <SubjectsCard subjects={subjects} busy={busy} />
          </div>

          <ChartCard
            title="Scheduled tests"
            description="Average score of these students in recent tests"
            busy={busy}
            table={
              <DataTable
                caption="Scheduled tests"
                columns={[
                  { key: "title", label: "Test" },
                  { key: "startsAt", label: "Date", format: dateLabel },
                  { key: "audience", label: "Assigned to" },
                  { key: "submitted", label: "Submitted", align: "right", format: (v, r) => `${v} / ${r.students}` },
                  { key: "averagePercentage", label: "Average", align: "right", format: formatPercent },
                ]}
                rows={tests}
              />
            }
          >
            <HBarChart
              items={tests.map((t) => ({
                key: t.id,
                label: t.title,
                sub: `${dateLabel(t.startsAt)} · ${t.submitted} of ${t.students} submitted`,
                value: t.averagePercentage,
                emptyValue: t.status === "closed" ? "—" : "Open",
              }))}
              format={formatPercent}
              empty="No scheduled tests in this period."
            />
          </ChartCard>

          <StudentsReportTable students={students} />
        </>
      )}
    </div>
  );
};

export default ReportsOverview;
