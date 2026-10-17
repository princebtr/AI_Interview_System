import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import toast from "react-hot-toast";
import { ArrowUpTrayIcon, KeyIcon, UserPlusIcon } from "@heroicons/react/20/solid";
import { buttonStyles } from "../../components/styles";
import api from "../../utils/axios";
import { useAuth } from "../../context/AuthContext";
import AddUserPanel from "../../components/admin/AddUserPanel";
import ResetPasswordPanel from "../../components/admin/ResetPasswordPanel";
import { Badge, Button, Card, PageHeader, SearchInput, Select } from "../../components/ui";
import { apiError, cx, formatDate, initials } from "../../utils/helpers";
import { ROLES, roleMeta } from "../../utils/roles";

const PAGE_SIZE = 50;

const byName = (a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" });

const Status = ({ user }) => {
  const [dot, text, label] = !user.lastLogin
    ? ["bg-slate-300", "text-slate-500", "Not signed in yet"]
    : user.mustChangePassword
      ? ["bg-amber-500", "text-slate-700", "Password not set"]
      : ["bg-emerald-500", "text-slate-700", "Active"];
  return (
    <span className={cx("inline-flex items-center gap-1.5 text-[13px] whitespace-nowrap", text)}>
      <span className={cx("size-1.5 rounded-full", dot)} />
      {label}
    </span>
  );
};

const SkeletonRows = () =>
  Array.from({ length: 5 }, (_, i) => (
    <tr key={i}>
      <td className="px-5 py-3.5" colSpan={6}>
        <div className="flex items-center gap-3">
          <div className="size-8 animate-pulse rounded-full bg-slate-100" />
          <div className="space-y-1.5">
            <div className="h-3 w-40 animate-pulse rounded bg-slate-100" />
            <div className="h-3 w-56 animate-pulse rounded bg-slate-100" />
          </div>
        </div>
      </td>
    </tr>
  ));

const Users = () => {
  const { user: me } = useAuth();
  const [params, setParams] = useSearchParams();
  const roleParam = params.get("role") ?? "";
  const role = ROLES.some((r) => r.value === roleParam) ? roleParam : "";
  const addParam = params.get("add");
  const adding = Boolean(addParam);
  const [cohort, setCohort] = useState("");
  const [resetting, setResetting] = useState(null);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState({ users: [], total: 0, counts: {} });
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [cohorts, setCohorts] = useState([]);
  const [cohortsLoaded, setCohortsLoaded] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const updateParams = (changes) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        Object.entries(changes).forEach(([key, value]) => (value ? next.set(key, value) : next.delete(key)));
        return next;
      },
      { replace: true }
    );
  const setAdding = (value) => updateParams({ add: value ? (value === true ? "student" : value) : null, cohort: null });

  // Debounce the search box so we don't query on every keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const paramsFor = useCallback(
    (offset) => ({
      limit: PAGE_SIZE,
      offset,
      ...(role && { role }),
      ...(cohort && { cohort }),
      ...(query && { q: query }),
    }),
    [role, cohort, query]
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get("/institution/users", { params: paramsFor(0) })
      .then(({ data }) => !cancelled && setResult(data))
      .catch((error) => !cancelled && toast.error(apiError(error, "Couldn't load users.")))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [paramsFor, reloadKey]);

  useEffect(() => {
    let cancelled = false;
    api
      .get("/institution/cohorts")
      .then(({ data }) => !cancelled && setCohorts(data.cohorts))
      .catch((error) => !cancelled && toast.error(apiError(error, "Couldn't load cohorts.")))
      .finally(() => !cancelled && setCohortsLoaded(true));
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const { data } = await api.get("/institution/users", {
        params: paramsFor(result.users.length),
      });
      setResult((prev) => ({ ...data, users: [...prev.users, ...data.users] }));
    } catch (error) {
      toast.error(apiError(error, "Couldn't load more users."));
    } finally {
      setLoadingMore(false);
    }
  };

  const selectRole = (value) => {
    updateParams({ role: value });
    // Only students belong to cohorts.
    if (value !== "" && value !== "student") setCohort("");
  };

  const clearFilters = () => {
    updateParams({ role: null });
    setCohort("");
    setSearch("");
    setQuery("");
  };

  const counts = result.counts ?? {};
  const tabs = [
    { value: "", label: "All", count: ROLES.reduce((n, r) => n + (counts[r.value] ?? 0), 0) },
    ...ROLES.map((r) => ({ value: r.value, label: r.plural, count: counts[r.value] ?? 0 })),
  ];
  const showCohortFilter = cohorts.length > 0 && (role === "" || role === "student");
  const filtered = Boolean(role || cohort || query);
  const institution = me?.institution?.name;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Administration"
        title="Users"
        description={`Add and manage the admins, educators and students${
          institution ? ` of ${institution}` : ""
        }. People sign in with the email and password you set.`}
        actions={
          <>
            <Link to="/users/import" className={buttonStyles({ variant: "secondary" })}>
              <ArrowUpTrayIcon className="size-4" />
              Import users
            </Link>
            <Button onClick={() => setAdding(true)}>
              <UserPlusIcon className="size-4" />
              Add user
            </Button>
          </>
        }
      />

      <Card>
        <div className="flex flex-col gap-3 border-b border-slate-100 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
          <div role="tablist" aria-label="Filter by role" className="-mx-1 flex gap-1 overflow-x-auto px-1">
            {tabs.map((tab) => {
              const active = role === tab.value;
              return (
                <button
                  key={tab.value || "all"}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => selectRole(tab.value)}
                  className={cx(
                    "flex h-8 shrink-0 items-center gap-2 rounded-md px-2.5 text-sm font-medium transition-colors",
                    active ? "bg-slate-100 text-slate-900" : "text-slate-500 hover:text-slate-800"
                  )}
                >
                  {tab.label}
                  <span
                    className={cx(
                      "min-w-5 rounded-full px-1.5 text-center text-[11px] tabular-nums",
                      active ? "bg-white text-slate-700 ring-1 ring-slate-200" : "bg-slate-100 text-slate-500"
                    )}
                  >
                    {tab.count}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="flex flex-col gap-2 sm:flex-row">
            {showCohortFilter && (
              <div className="sm:w-48">
                <label htmlFor="cohort-filter" className="sr-only">
                  Filter by cohort
                </label>
                <Select
                  id="cohort-filter"
                  value={cohort}
                  onChange={(e) => setCohort(e.target.value)}
                  compact
                >
                  <option value="">All cohorts</option>
                  {cohorts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.studentCount})
                    </option>
                  ))}
                </Select>
              </div>
            )}
            <SearchInput
              id="user-search"
              label="Search users"
              className="sm:w-64"
              value={search}
              maxLength={100}
              placeholder="Search name or email"
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-[12px] text-slate-500">
                <th className="px-5 py-2.5 font-medium">User</th>
                <th className="px-5 py-2.5 font-medium">Role</th>
                <th className="hidden px-5 py-2.5 font-medium md:table-cell">Cohort</th>
                <th className="hidden px-5 py-2.5 font-medium sm:table-cell">Status</th>
                <th className="hidden px-5 py-2.5 text-right font-medium lg:table-cell">Added</th>
                <th className="w-12 px-3 py-2.5">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <SkeletonRows />
              ) : result.users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center">
                    <p className="text-sm font-medium text-slate-900">
                      {filtered ? "No users match these filters" : "No users yet"}
                    </p>
                    <p className="mt-1 text-[13px] text-slate-500">
                      {filtered
                        ? "Try a different search or clear the filters."
                        : "Add your first educator or student to get started."}
                    </p>
                    <div className="mt-4">
                      {filtered ? (
                        <Button variant="secondary" onClick={clearFilters}>
                          Clear filters
                        </Button>
                      ) : (
                        <Button onClick={() => setAdding(true)}>
                          <UserPlusIcon className="size-4" />
                          Add user
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ) : (
                result.users.map((u) => {
                  const meta = roleMeta(u.role);
                  return (
                    <tr key={u.id}>
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-3">
                          <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[11px] font-semibold text-slate-600">
                            {initials(u.name)}
                          </span>
                          <div className="min-w-0">
                            <p className="flex items-center gap-2 font-medium text-slate-900">
                              <span className="truncate">{u.name}</span>
                              {u.id === me?.id && <Badge>You</Badge>}
                            </p>
                            <p className="truncate text-[13px] text-slate-500">{u.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-3">
                        <Badge tone={meta.tone}>{meta.label}</Badge>
                      </td>
                      <td className="hidden px-5 py-3 text-slate-700 md:table-cell">
                        {u.cohort?.name ?? <span className="text-slate-300">—</span>}
                      </td>
                      <td className="hidden px-5 py-3 sm:table-cell">
                        <Status user={u} />
                      </td>
                      <td className="hidden px-5 py-3 text-right text-slate-500 tabular-nums lg:table-cell">
                        {formatDate(u.createdAt)}
                      </td>
                      <td className="px-3 py-3 text-right">
                        {u.id !== me?.id && (
                          <button
                            type="button"
                            onClick={() => setResetting(u)}
                            aria-label={`Reset password for ${u.name}`}
                            title="Reset password"
                            className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
                          >
                            <KeyIcon className="size-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {!loading && result.users.length > 0 && (
          <div className="flex items-center justify-between gap-3 rounded-b-lg border-t border-slate-100 bg-slate-50/70 px-5 py-3 text-[13px] text-slate-500">
            <span className="tabular-nums">
              Showing {result.users.length} of {result.total}
            </span>
            {result.users.length < result.total && (
              <Button variant="secondary" size="sm" onClick={loadMore} loading={loadingMore}>
                Load more
              </Button>
            )}
          </div>
        )}
      </Card>

      {/* Wait for cohorts so the form knows whether to offer "choose" or "create". */}
      {adding && cohortsLoaded && (
        <AddUserPanel
          cohorts={cohorts}
          initialRole={addParam}
          initialCohortId={params.get("cohort") ?? ""}
          onClose={() => setAdding(false)}
          onCohortCreated={(c) =>
            setCohorts((prev) => [...prev, { studentCount: 0, ...c }].sort(byName))
          }
          onCreated={() => setReloadKey((k) => k + 1)}
        />
      )}

      {resetting && (
        <ResetPasswordPanel
          user={resetting}
          onClose={() => setResetting(null)}
          onReset={() => setReloadKey((k) => k + 1)}
        />
      )}
    </div>
  );
};

export default Users;
