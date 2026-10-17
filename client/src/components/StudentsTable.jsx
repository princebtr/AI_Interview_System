import { useEffect, useState } from "react";
import { AcademicCapIcon } from "@heroicons/react/24/outline";
import { useApi } from "../hooks/useApi";
import { Button, SearchInput, Select } from "./ui";
import { EmptyState, LoadError, ScoreBar } from "./data";
import { cx, initials } from "../utils/helpers";
import { formatPercent } from "../utils/scores";
import { timeAgo } from "../utils/time";

const PAGE_SIZE = 50;
const MAX_LIMIT = 200;

const SignInStatus = ({ student }) => {
  const [dot, label] = !student.lastLogin
    ? ["bg-slate-300", "Not signed in yet"]
    : student.mustChangePassword
      ? ["bg-amber-500", "Password not set"]
      : ["bg-emerald-500", "Active"];
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px] whitespace-nowrap text-slate-600">
      <span className={cx("size-1.5 rounded-full", dot)} />
      {label}
    </span>
  );
};

/**
 * Students of the signed-in user's institution with their practice stats.
 * Pass `cohortId` to lock the table to one cohort; otherwise a cohort filter is shown.
 */
const StudentsTable = ({ cohortId, showCohort = true }) => {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [cohort, setCohort] = useState("");
  const [pages, setPages] = useState(1);
  const cohorts = useApi(cohortId ? null : "/institution/cohorts");

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  // A new filter starts again from the first page.
  useEffect(() => setPages(1), [query, cohort, cohortId]);

  const activeCohort = cohortId || cohort;
  const { data, loading, error, reload } = useApi("/teaching/students", {
    limit: Math.min(MAX_LIMIT, PAGE_SIZE * pages),
    ...(activeCohort && { cohort: activeCohort }),
    ...(query && { q: query }),
  });

  const students = data?.students ?? [];
  const total = data?.total ?? 0;
  const filtered = Boolean(query || cohort);
  const canLoadMore = students.length < total && PAGE_SIZE * pages < MAX_LIMIT;

  return (
    <div>
      <div className="flex flex-col gap-2 border-b border-slate-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-end">
        {!cohortId && (cohorts.data?.cohorts?.length ?? 0) > 0 && (
          <div className="sm:w-48">
            <label htmlFor="students-cohort" className="sr-only">
              Filter by cohort
            </label>
            <Select
              id="students-cohort"
              value={cohort}
              onChange={(e) => setCohort(e.target.value)}
              compact
            >
              <option value="">All cohorts</option>
              {cohorts.data.cohorts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </div>
        )}
        <SearchInput
          id="students-search"
          label="Search students"
          className="sm:w-64"
          value={search}
          maxLength={100}
          placeholder="Search name or email"
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {error && !data ? (
        <div className="p-5">
          <LoadError onRetry={reload} />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-[12px] text-slate-500">
                <th className="px-5 py-2.5 font-medium">Student</th>
                {showCohort && <th className="hidden px-5 py-2.5 font-medium md:table-cell">Cohort</th>}
                <th className="hidden px-5 py-2.5 font-medium lg:table-cell">Status</th>
                <th className="px-5 py-2.5 text-right font-medium">Sessions</th>
                <th className="hidden px-5 py-2.5 font-medium sm:table-cell">Avg score</th>
                <th className="hidden px-5 py-2.5 text-right font-medium md:table-cell">Last practice</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && !data ? (
                Array.from({ length: 4 }, (_, i) => (
                  <tr key={i}>
                    <td colSpan={6} className="px-5 py-3.5">
                      <div className="h-4 w-56 animate-pulse rounded bg-slate-100" />
                    </td>
                  </tr>
                ))
              ) : students.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <EmptyState
                      icon={AcademicCapIcon}
                      title={filtered ? "No students match these filters" : "No students yet"}
                      description={
                        filtered
                          ? "Try a different search or cohort."
                          : "Students appear here once an admin adds them."
                      }
                    />
                  </td>
                </tr>
              ) : (
                students.map((s) => (
                  <tr key={s.id}>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-3">
                        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[11px] font-semibold text-slate-600">
                          {initials(s.name)}
                        </span>
                        <div className="min-w-0">
                          <p className="truncate font-medium text-slate-900">{s.name}</p>
                          <p className="truncate text-[13px] text-slate-500">{s.email}</p>
                        </div>
                      </div>
                    </td>
                    {showCohort && (
                      <td className="hidden px-5 py-3 text-slate-700 md:table-cell">
                        {s.cohort?.name ?? <span className="text-slate-300">—</span>}
                      </td>
                    )}
                    <td className="hidden px-5 py-3 lg:table-cell">
                      <SignInStatus student={s} />
                    </td>
                    <td className="px-5 py-3 text-right text-slate-700 tabular-nums">{s.attempts}</td>
                    <td className="hidden px-5 py-3 sm:table-cell">
                      <div className="flex items-center gap-3">
                        <ScoreBar value={s.averageScore} className="w-24" />
                        <span className="w-10 text-right text-slate-700 tabular-nums">
                          {formatPercent(s.averageScore)}
                        </span>
                      </div>
                    </td>
                    <td className="hidden px-5 py-3 text-right text-slate-500 md:table-cell">
                      {s.lastPracticeAt ? timeAgo(s.lastPracticeAt) : "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {students.length > 0 && (
        <div className="flex items-center justify-between gap-3 rounded-b-lg border-t border-slate-100 bg-slate-50/70 px-5 py-3 text-[13px] text-slate-500">
          <span className="tabular-nums">
            Showing {students.length} of {total}
          </span>
          {canLoadMore && (
            <Button variant="secondary" size="sm" loading={loading} onClick={() => setPages((p) => p + 1)}>
              Load more
            </Button>
          )}
        </div>
      )}
    </div>
  );
};

export default StudentsTable;
