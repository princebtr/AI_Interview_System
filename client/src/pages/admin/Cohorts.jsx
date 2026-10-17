import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import toast from "react-hot-toast";
import { PlusIcon, TrashIcon } from "@heroicons/react/20/solid";
import { UserGroupIcon } from "@heroicons/react/24/outline";
import api from "../../utils/axios";
import { useApi } from "../../hooks/useApi";
import { Button, Card, CardFooter, CardHeader, Input, PageHeader } from "../../components/ui";
import { EmptyState, LoadError, LoadingBlock, ScoreBar } from "../../components/data";
import { apiError, formatDate } from "../../utils/helpers";
import { formatPercent } from "../../utils/scores";

const NewCohortForm = ({ onCreated, onCancel }) => {
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setError("Enter a cohort name");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const { data } = await api.post("/institution/cohorts", { name: name.trim() });
      toast.success(`Cohort "${data.cohort.name}" created`);
      onCreated();
    } catch (err) {
      setError(apiError(err, "Couldn't create the cohort. Try again."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <form onSubmit={submit} noValidate>
        <CardHeader title="New cohort" description="Students who study together, e.g. a batch or class." />
        <div className="p-5">
          <Input
            id="cohort-name"
            label="Name"
            placeholder="e.g. CSE-2027"
            maxLength={60}
            autoFocus
            value={name}
            error={error}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <CardFooter>
          <p className="text-[13px] text-slate-500">You can add students to it straight away.</p>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" loading={saving}>
              Create cohort
            </Button>
          </div>
        </CardFooter>
      </form>
    </Card>
  );
};

const Cohorts = () => {
  const [params, setParams] = useSearchParams();
  const creating = params.get("new") === "1";
  const { data, error, loading, reload } = useApi("/institution/cohorts");
  const [deleting, setDeleting] = useState(null);

  const setCreating = (open) => setParams(open ? { new: "1" } : {}, { replace: true });

  const remove = async (cohort) => {
    if (!window.confirm(`Delete the cohort "${cohort.name}"? This can't be undone.`)) return;
    setDeleting(cohort.id);
    try {
      await api.delete(`/institution/cohorts/${cohort.id}`);
      toast.success(`Cohort "${cohort.name}" deleted`);
      reload();
    } catch (err) {
      toast.error(apiError(err, "Couldn't delete the cohort."));
    } finally {
      setDeleting(null);
    }
  };

  const cohorts = data?.cohorts ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Academics"
        title="Cohorts"
        description="Group students who study together. Every student belongs to exactly one cohort."
        actions={
          !creating && (
            <Button onClick={() => setCreating(true)}>
              <PlusIcon className="size-4" />
              New cohort
            </Button>
          )
        }
      />

      {creating && (
        <NewCohortForm
          onCancel={() => setCreating(false)}
          onCreated={() => {
            setCreating(false);
            reload();
          }}
        />
      )}

      {error && !data ? (
        <LoadError onRetry={reload} />
      ) : (
        <Card>
          {loading && !data ? (
            <div className="space-y-3 p-5">
              {[0, 1, 2].map((i) => (
                <LoadingBlock key={i} className="h-10" />
              ))}
            </div>
          ) : cohorts.length === 0 ? (
            <EmptyState
              icon={UserGroupIcon}
              title="No cohorts yet"
              description="Create a cohort for each batch or class, then add students to it."
              action={
                !creating && (
                  <Button onClick={() => setCreating(true)}>
                    <PlusIcon className="size-4" />
                    New cohort
                  </Button>
                )
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-[12px] text-slate-500">
                    <th className="px-5 py-2.5 font-medium">Cohort</th>
                    <th className="px-5 py-2.5 text-right font-medium">Students</th>
                    <th className="hidden px-5 py-2.5 text-right font-medium sm:table-cell">Signed in</th>
                    <th className="hidden px-5 py-2.5 font-medium md:table-cell">Avg practice score</th>
                    <th className="hidden px-5 py-2.5 text-right font-medium lg:table-cell">Created</th>
                    <th className="w-12 px-3 py-2.5">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {cohorts.map((c) => (
                    <tr key={c.id} className="transition-colors hover:bg-slate-50">
                      <td className="px-5 py-3">
                        <Link to={`/cohorts/${c.id}`} className="font-medium text-slate-900 hover:text-accent-700">
                          {c.name}
                        </Link>
                      </td>
                      <td className="px-5 py-3 text-right text-slate-700 tabular-nums">{c.studentCount}</td>
                      <td className="hidden px-5 py-3 text-right text-slate-500 tabular-nums sm:table-cell">
                        {c.activated} / {c.studentCount}
                      </td>
                      <td className="hidden px-5 py-3 md:table-cell">
                        <div className="flex items-center gap-3">
                          <ScoreBar value={c.averageScore} className="w-32" />
                          <span className="w-10 text-right text-slate-700 tabular-nums">
                            {formatPercent(c.averageScore)}
                          </span>
                        </div>
                      </td>
                      <td className="hidden px-5 py-3 text-right text-slate-500 tabular-nums lg:table-cell">
                        {formatDate(c.createdAt)}
                      </td>
                      <td className="px-3 py-3 text-right">
                        {c.studentCount === 0 && (
                          <button
                            type="button"
                            onClick={() => remove(c)}
                            disabled={deleting === c.id}
                            aria-label={`Delete ${c.name}`}
                            title="Delete empty cohort"
                            className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                          >
                            <TrashIcon className="size-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <p className="text-[13px] text-slate-500">
        Departments and programs are coming soon. For now, name cohorts so they're easy to tell apart,
        e.g. <span className="font-medium text-slate-700">CSE-2027</span>.
      </p>
    </div>
  );
};

export default Cohorts;
