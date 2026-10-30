import { useState } from "react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import { ChevronRightIcon, PencilSquareIcon, PlusIcon, TrashIcon } from "@heroicons/react/20/solid";
import { RectangleGroupIcon } from "@heroicons/react/24/outline";
import api from "../../utils/axios";
import { useApi } from "../../hooks/useApi";
import { Badge, Button, Card, PageHeader } from "../../components/ui";
import { EmptyState, LoadError, LoadingBlock, ScoreBar } from "../../components/data";
import { apiError, cx } from "../../utils/helpers";
import { formatPercent } from "../../utils/scores";
import { LEVELS, LEVEL_META, childLevel, flatten } from "../../utils/structure";

const LEVEL_TONES = { batch: "brand", department: "blue", section: "violet", cohort: "neutral" };
const INDENT = { batch: 0, department: 1, section: 2, cohort: 3 };

/** One-line name form, used to add a group or rename one. */
const NameForm = ({ level, initial = "", submitLabel, onSubmit, onCancel, depth }) => {
  const [name, setName] = useState(initial);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const meta = LEVEL_META[level];

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setError(`Enter a ${meta.label.toLowerCase()} name`);
      return;
    }
    setSaving(true);
    setError("");
    try {
      await onSubmit(name.trim());
    } catch (err) {
      setError(apiError(err, "Couldn't save. Try again."));
      setSaving(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      noValidate
      className="flex flex-col gap-2 bg-accent-50/40 px-5 py-3 sm:flex-row sm:items-start"
      style={{ paddingLeft: `calc(1.25rem + ${depth * 1.5}rem)` }}
    >
      <div className="min-w-0 flex-1">
        <label htmlFor={`name-${level}`} className="sr-only">
          {meta.label} name
        </label>
        <input
          id={`name-${level}`}
          value={name}
          maxLength={60}
          autoFocus
          placeholder={`${meta.label} name, ${meta.example}`}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `name-${level}-error` : undefined}
          onChange={(e) => {
            setError("");
            setName(e.target.value);
          }}
          onKeyDown={(e) => e.key === "Escape" && onCancel()}
          className={cx(
            "block h-9 w-full rounded-md border bg-white px-3 text-sm text-slate-900 shadow-xs placeholder:text-slate-400 focus:ring-3 focus:outline-none",
            error
              ? "border-red-400 focus:border-red-500 focus:ring-red-500/15"
              : "border-slate-300 focus:border-accent-600 focus:ring-accent-600/15"
          )}
        />
        {error && (
          <p id={`name-${level}-error`} className="mt-1 text-[13px] text-red-600">
            {error}
          </p>
        )}
      </div>
      <div className="flex gap-2">
        <Button variant="secondary" size="sm" className="h-9" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" size="sm" className="h-9" loading={saving}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
};

const IconButton = ({ label, onClick, disabled, danger, children }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    aria-label={label}
    title={label}
    className={cx(
      "rounded-md p-1.5 text-slate-400 transition-colors disabled:opacity-50",
      danger ? "hover:bg-red-50 hover:text-red-600" : "hover:bg-slate-100 hover:text-slate-700"
    )}
  >
    {children}
  </button>
);

const Structure = () => {
  const { data, error, loading, reload } = useApi("/institution/structure");
  const [expanded, setExpanded] = useState(() => new Set());
  // {mode: "add", level, parentId} | {mode: "rename", node}
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(null);

  const batches = data?.batches ?? [];
  const counts = data?.counts;

  const toggle = (id, open) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (open ?? !next.has(id)) next.add(id);
      else next.delete(id);
      return next;
    });

  const create = async (level, parentId, name) => {
    const { data: created } = await api.post("/institution/structure", {
      level,
      name,
      ...(parentId && { parentId }),
    });
    toast.success(`${LEVEL_META[level].label} "${created.node.name}" created`);
    if (parentId) toggle(parentId, true);
    setEditing(null);
    reload();
  };

  const rename = async (node, name) => {
    await api.patch(`/institution/structure/${node.level}/${node.id}`, { name });
    toast.success(`Renamed to "${name}"`);
    setEditing(null);
    reload();
  };

  const remove = async (node) => {
    const noun = LEVEL_META[node.level].label.toLowerCase();
    if (!window.confirm(`Delete the ${noun} "${node.label}"? This can't be undone.`)) return;
    setBusy(node.id);
    try {
      await api.delete(`/institution/structure/${node.level}/${node.id}`);
      toast.success(`Deleted "${node.name}"`);
      reload();
    } catch (err) {
      toast.error(apiError(err, `Couldn't delete the ${noun}.`));
    } finally {
      setBusy(null);
    }
  };

  const addForm = (level, parentId) =>
    editing?.mode === "add" && editing.level === level && editing.parentId === parentId ? (
      <NameForm
        key={`add-${level}-${parentId}`}
        level={level}
        depth={INDENT[level]}
        submitLabel={`Add ${LEVEL_META[level].label.toLowerCase()}`}
        onCancel={() => setEditing(null)}
        onSubmit={(name) => create(level, parentId, name)}
      />
    ) : null;

  const renderNode = (node) => {
    const child = childLevel(node.level);
    const kids = node.children ?? [];
    const open = expanded.has(node.id);
    const meta = LEVEL_META[node.level];

    if (editing?.mode === "rename" && editing.node.id === node.id) {
      return (
        <NameForm
          key={node.id}
          level={node.level}
          initial={node.name}
          depth={INDENT[node.level]}
          submitLabel="Rename"
          onCancel={() => setEditing(null)}
          onSubmit={(name) => rename(node, name)}
        />
      );
    }

    return (
      <div key={node.id} role="treeitem" aria-expanded={child ? open : undefined} aria-level={INDENT[node.level] + 1}>
        <div className="group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-5 py-2.5 transition-colors hover:bg-slate-50 md:grid-cols-[minmax(0,1fr)_5rem_6rem_10rem_6.5rem]">
          <div className="flex min-w-0 items-center gap-1.5" style={{ paddingLeft: `${INDENT[node.level] * 1.5}rem` }}>
            {child ? (
              <button
                type="button"
                onClick={() => toggle(node.id)}
                aria-label={`${open ? "Collapse" : "Expand"} ${node.name}`}
                className="rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              >
                <ChevronRightIcon className={cx("size-4 transition-transform", open && "rotate-90")} />
              </button>
            ) : (
              <span className="w-5" aria-hidden="true" />
            )}
            <Link
              to={`/structure/${node.level}/${node.id}`}
              className="truncate font-medium text-slate-900 hover:text-accent-700"
            >
              {node.name}
            </Link>
            <Badge tone={LEVEL_TONES[node.level]} className="ml-1 hidden sm:inline-flex">
              {meta.label}
            </Badge>
            {child && kids.length > 0 && (
              <span className="ml-1 hidden text-[12px] text-slate-400 lg:inline">
                {kids.length} {(kids.length === 1 ? LEVEL_META[child].label : LEVEL_META[child].plural).toLowerCase()}
              </span>
            )}
          </div>
          <span className="hidden text-right text-slate-700 tabular-nums md:block">{node.studentCount}</span>
          <span className="hidden text-right text-slate-500 tabular-nums md:block">
            {node.activated} / {node.studentCount}
          </span>
          <div className="hidden items-center gap-2 md:flex">
            <ScoreBar value={node.averageScore} className="w-20" />
            <span className="w-10 text-right text-[13px] text-slate-700 tabular-nums">
              {formatPercent(node.averageScore)}
            </span>
          </div>
          <div className="flex justify-end gap-0.5">
            {child && (
              <IconButton
                label={`Add a ${LEVEL_META[child].label.toLowerCase()} to ${node.name}`}
                onClick={() => {
                  toggle(node.id, true);
                  setEditing({ mode: "add", level: child, parentId: node.id });
                }}
              >
                <PlusIcon className="size-4" />
              </IconButton>
            )}
            <IconButton label={`Rename ${node.name}`} onClick={() => setEditing({ mode: "rename", node })}>
              <PencilSquareIcon className="size-4" />
            </IconButton>
            {node.studentCount === 0 && kids.length === 0 && (
              <IconButton label={`Delete ${node.name}`} danger disabled={busy === node.id} onClick={() => remove(node)}>
                <TrashIcon className="size-4" />
              </IconButton>
            )}
          </div>
        </div>
        {child && open && (
          <div role="group">
            {kids.map(renderNode)}
            {addForm(child, node.id)}
            {kids.length === 0 && !(editing?.mode === "add" && editing.parentId === node.id) && (
              <p
                className="px-5 py-2 text-[13px] text-slate-400"
                style={{ paddingLeft: `calc(1.25rem + ${INDENT[child] * 1.5 + 1.625}rem)` }}
              >
                No {LEVEL_META[child].plural.toLowerCase()} yet.{" "}
                <button
                  type="button"
                  className="font-medium text-accent-700 hover:text-accent-800"
                  onClick={() => setEditing({ mode: "add", level: child, parentId: node.id })}
                >
                  Add one
                </button>
              </p>
            )}
          </div>
        )}
      </div>
    );
  };

  const all = flatten(batches);
  const allOpen = all.length > 0 && all.every((n) => !n.children || expanded.has(n.id));

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Academics"
        title="Academic structure"
        description="Batch → Department → Section → Cohort. Every student sits in one cohort, and tests can be assigned to any level."
        actions={
          <Button onClick={() => setEditing({ mode: "add", level: "batch", parentId: null })}>
            <PlusIcon className="size-4" />
            New batch
          </Button>
        }
      />

      {counts && (
        <div className="flex flex-wrap gap-2 text-[13px] text-slate-600">
          {LEVELS.map((level) => {
            const n = counts[level === "batch" ? "batches" : `${level}s`] ?? 0;
            return (
              <Badge key={level} tone={LEVEL_TONES[level]}>
                {n} {(n === 1 ? LEVEL_META[level].label : LEVEL_META[level].plural).toLowerCase()}
              </Badge>
            );
          })}
        </div>
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
          ) : batches.length === 0 && editing?.level !== "batch" ? (
            <EmptyState
              icon={RectangleGroupIcon}
              title="No batches yet"
              description="Start with a batch, e.g. 2023-2027, then add its departments, sections and cohorts."
              action={
                <Button onClick={() => setEditing({ mode: "add", level: "batch", parentId: null })}>
                  <PlusIcon className="size-4" />
                  New batch
                </Button>
              }
            />
          ) : (
            <>
              <div className="hidden grid-cols-[minmax(0,1fr)_5rem_6rem_10rem_6.5rem] gap-3 border-b border-slate-100 px-5 py-2.5 text-[12px] font-medium text-slate-500 md:grid">
                <span className="flex items-center gap-3">
                  Group
                  {all.length > 0 && (
                    <button
                      type="button"
                      className="font-medium text-accent-700 hover:text-accent-800"
                      onClick={() =>
                        setExpanded(allOpen ? new Set() : new Set(all.filter((n) => n.children).map((n) => n.id)))
                      }
                    >
                      {allOpen ? "Collapse all" : "Expand all"}
                    </button>
                  )}
                </span>
                <span className="text-right">Students</span>
                <span className="text-right">Signed in</span>
                <span>Avg practice score</span>
                <span className="sr-only">Actions</span>
              </div>
              <div role="tree" aria-label="Academic structure" className="divide-y divide-slate-100">
                {batches.map(renderNode)}
                {addForm("batch", null)}
              </div>
            </>
          )}
        </Card>
      )}

      <p className="text-[13px] text-slate-500">
        Names only need to be unique within their parent, so every batch can have its own{" "}
        <span className="font-medium text-slate-700">Computer Science</span> department with a{" "}
        <span className="font-medium text-slate-700">Section A</span>.
      </p>
    </div>
  );
};

export default Structure;
