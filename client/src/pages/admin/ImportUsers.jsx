import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import {
  ArrowDownTrayIcon,
  CheckCircleIcon,
  DocumentArrowUpIcon,
  ExclamationTriangleIcon,
} from "@heroicons/react/20/solid";
import api from "../../utils/axios";
import { Badge, Button, Card, CardFooter, CardHeader, PageHeader } from "../../components/ui";
import { buttonStyles } from "../../components/styles";
import { apiError, cx } from "../../utils/helpers";
import { roleMeta } from "../../utils/roles";
import { exportUsers } from "../../utils/users";
import { LEVEL_META } from "../../utils/structure";

const MAX_BYTES = 1024 * 1024;
const TEMPLATE = [
  "name,email,role,password,batch,department,section,cohort",
  "Rahul Sharma,rahul@example.com,student,Temp@1234,2023-2027,Computer Science,A,Lab group 1",
  "Priya Singh,priya@example.com,student,,2023-2027,Computer Science,A,Lab group 2",
  "Amit Kumar,amit@example.com,educator,,,,,",
].join("\n");

/** "Department 2023-2027 · Computer Science, Section ..." from [{level, label}]. */
const groupList = (groups) => groups.map((g) => `${LEVEL_META[g.level].label} ${g.label}`).join(", ");

const csvCell = (value) => {
  const text = String(value ?? "");
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

const download = (filename, text) => {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

const Steps = ({ current }) => {
  const steps = ["Upload file", "Review", "Done"];
  return (
    <ol className="flex items-center gap-2 text-[13px]" aria-label="Import progress">
      {steps.map((label, i) => (
        <li key={label} className="flex items-center gap-2">
          <span
            aria-current={i === current ? "step" : undefined}
            className={cx(
              "flex size-6 items-center justify-center rounded-full text-[12px] font-semibold tabular-nums",
              i < current
                ? "bg-accent-600 text-white"
                : i === current
                  ? "bg-accent-50 text-accent-700 ring-1 ring-accent-600/30"
                  : "bg-slate-100 text-slate-500"
            )}
          >
            {i + 1}
          </span>
          <span className={i === current ? "font-medium text-slate-900" : "text-slate-500"}>{label}</span>
          {i < steps.length - 1 && <span className="mx-1 h-px w-6 bg-slate-200" aria-hidden="true" />}
        </li>
      ))}
    </ol>
  );
};

const MODES = [
  {
    value: "add",
    label: "Add new users",
    description: "Create accounts for people who aren't in Cohortix yet.",
  },
  {
    value: "update",
    label: "Update existing users",
    description: "Change names, roles, placements or passwords. People are matched by email.",
  },
];

const ImportUsers = () => {
  const inputRef = useRef(null);
  const [mode, setMode] = useState("add");
  const [exporting, setExporting] = useState(false);
  const [file, setFile] = useState(null);
  const [createGroups, setCreateGroups] = useState(false);
  const [report, setReport] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [problemsOnly, setProblemsOnly] = useState(false);

  const send = async (chosen, { commit, withGroups, as = mode }) => {
    const form = new FormData();
    form.append("file", chosen);
    form.append("mode", as);
    form.append("commit", commit ? "true" : "false");
    form.append("createGroups", withGroups ? "true" : "false");
    const { data } = await api.post("/institution/users/import", form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 120000, // hashing hundreds of passwords takes a while
    });
    return data;
  };

  const validate = async (chosen, withGroups = createGroups, as = mode) => {
    if (!chosen) return;
    if (!/\.csv$/i.test(chosen.name)) {
      toast.error("Choose a .csv file. In Excel, use File → Save As → CSV.");
      return;
    }
    if (chosen.size > MAX_BYTES) {
      toast.error("That file is larger than 1 MB. Split it into smaller files.");
      return;
    }
    setBusy(true);
    try {
      const data = await send(chosen, { commit: false, withGroups, as });
      setFile(chosen);
      setReport(data);
      // Add: start on the problems. Update: start on what will change (and problems).
      setProblemsOnly(data.mode === "update" || data.summary.invalid > 0);
    } catch (error) {
      toast.error(apiError(error, "Couldn't read that file."));
    } finally {
      setBusy(false);
    }
  };

  const runImport = async () => {
    setBusy(true);
    try {
      const data = await send(file, { commit: true, withGroups: createGroups });
      setResult(data);
      toast.success(
        data.mode === "update"
          ? `Updated ${data.updated} user${data.updated === 1 ? "" : "s"}`
          : `Imported ${data.created} user${data.created === 1 ? "" : "s"}`
      );
    } catch (error) {
      toast.error(apiError(error, "The import failed. Nothing was changed."));
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setFile(null);
    setReport(null);
    setResult(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const toggleCreateGroups = (checked) => {
    setCreateGroups(checked);
    if (file) validate(file, checked);
  };

  const downloadExport = async () => {
    setExporting(true);
    try {
      await exportUsers();
    } catch (error) {
      toast.error(apiError(error, "Couldn't export the users."));
    } finally {
      setExporting(false);
    }
  };

  const downloadCredentials = () => {
    const rows = [["name", "email", "password"], ...result.credentials.map((c) => [c.name, c.email, c.password])];
    download("sign-in-details.csv", rows.map((r) => r.map(csvCell).join(",")).join("\n"));
  };

  const step = result ? 2 : report ? 1 : 0;
  const shown = (r) => r.errors.length || (report.mode === "update" && r.changes.length);
  const rows = report ? (problemsOnly ? report.rows.filter(shown) : report.rows) : [];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Users"
        title="Import users"
        description="Add many people at once, or update existing ones from an edited export. Every row is checked before anything changes."
        actions={<Steps current={step} />}
      />

      {step === 0 && (
        <fieldset className="space-y-2">
          <legend className="mb-2 text-sm font-semibold text-slate-800">What do you want to do?</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            {MODES.map((m) => (
              <label
                key={m.value}
                className={cx(
                  "flex cursor-pointer items-start gap-3 rounded-lg border bg-white p-4 transition-colors",
                  mode === m.value ? "border-accent-600 ring-1 ring-accent-600" : "border-slate-200 hover:border-slate-300"
                )}
              >
                <input
                  type="radio"
                  name="import-mode"
                  value={m.value}
                  checked={mode === m.value}
                  onChange={() => setMode(m.value)}
                  className="mt-0.5 size-4 accent-accent-700"
                />
                <span>
                  <span className="block text-sm font-semibold text-slate-900">{m.label}</span>
                  <span className="block text-[13px] text-slate-500">{m.description}</span>
                </span>
              </label>
            ))}
          </div>
          {mode === "update" && (
            <div className="flex flex-col gap-3 rounded-lg border border-accent-200 bg-accent-50/60 p-4 text-[13px] text-slate-700 sm:flex-row sm:items-center sm:justify-between">
              <ol className="list-decimal space-y-0.5 pl-4">
                <li>Export your users (or filter them on the Users page and export there).</li>
                <li>Edit names, roles, placements, or set a password. Leave emails as they are.</li>
                <li>Upload the file here. You'll see every change before anything is saved.</li>
              </ol>
              <Button variant="secondary" onClick={downloadExport} loading={exporting} className="shrink-0">
                {!exporting && <ArrowDownTrayIcon className="size-4" />}
                Export all users
              </Button>
            </div>
          )}
        </fieldset>
      )}

      {step === 0 && (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader title="Upload a CSV file" description="Up to 500 rows and 1 MB per file." />
            <div className="p-5">
              <label
                htmlFor="import-file"
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  validate(e.dataTransfer.files?.[0]);
                }}
                className={cx(
                  "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors",
                  dragging ? "border-accent-500 bg-accent-50" : "border-slate-300 hover:border-slate-400 hover:bg-slate-50"
                )}
              >
                <DocumentArrowUpIcon className="size-8 text-slate-400" />
                <span className="mt-3 text-sm font-medium text-slate-900">
                  {busy ? "Checking your file…" : "Drop your CSV here, or click to choose"}
                </span>
                <span className="mt-1 text-[13px] text-slate-500">
                  Columns: name, email, role, password, batch, department, section, cohort
                </span>
                <input
                  ref={inputRef}
                  id="import-file"
                  type="file"
                  accept=".csv,text/csv"
                  className="sr-only"
                  disabled={busy}
                  onChange={(e) => validate(e.target.files?.[0])}
                />
              </label>
              <label className="mt-4 flex items-start gap-2.5 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={createGroups}
                  onChange={(e) => setCreateGroups(e.target.checked)}
                  className="mt-0.5 size-4 rounded border-slate-300 accent-accent-600"
                />
                <span>
                  Create batches, departments, sections and cohorts that don't exist yet
                  <span className="block text-[13px] text-slate-500">
                    Otherwise rows naming an unknown group are flagged so you can fix typos first.
                  </span>
                </span>
              </label>
            </div>
          </Card>

          <Card>
            <CardHeader title="File format" />
            <div className="space-y-3 p-5 text-[13px] leading-relaxed text-slate-600">
              <ul className="list-disc space-y-1.5 pl-4">
                <li>
                  <span className="font-medium text-slate-800">role</span> is admin, educator or student.
                </li>
                <li>
                  <span className="font-medium text-slate-800">batch, department, section</span> and{" "}
                  <span className="font-medium text-slate-800">cohort</span> are required for students and ignored
                  for everyone else. Names only need to be unique within their parent.
                </li>
                {mode === "add" ? (
                  <>
                    <li>
                      <span className="font-medium text-slate-800">password</span> is optional. Leave it blank and
                      we'll generate one.
                    </li>
                    <li>Everyone chooses their own password at first sign-in.</li>
                  </>
                ) : (
                  <>
                    <li>
                      <span className="font-medium text-slate-800">email</span> picks who is updated, so don't change
                      it. Rows for emails that aren't in your institution are skipped.
                    </li>
                    <li>
                      <span className="font-medium text-slate-800">password</span>: leave it blank to keep theirs. A
                      new one signs them out and they choose their own at next sign-in.
                    </li>
                    <li>Changing someone's role signs them out. You can't change your own role here.</li>
                  </>
                )}
              </ul>
              <Button variant="secondary" onClick={() => download("users-template.csv", TEMPLATE)}>
                <ArrowDownTrayIcon className="size-4" />
                Download template
              </Button>
            </div>
          </Card>
        </div>
      )}

      {step === 1 && (
        <Card>
          <CardHeader
            title={file?.name ?? "Review"}
            description={`${report.summary.total} rows checked · ${report.mode === "update" ? "updating existing users" : "adding new users"}`}
            action={
              <div className="flex flex-wrap justify-end gap-2">
                {report.mode === "update" ? (
                  <>
                    <Badge tone="success">{report.summary.changing} to update</Badge>
                    {report.summary.valid - report.summary.changing > 0 && (
                      <Badge>{report.summary.valid - report.summary.changing} unchanged</Badge>
                    )}
                  </>
                ) : (
                  <Badge tone="success">{report.summary.valid} ready</Badge>
                )}
                {report.summary.invalid > 0 && <Badge tone="danger">{report.summary.invalid} with problems</Badge>}
              </div>
            }
          />

          {(report.missingGroups.length > 0 || report.newGroups.length > 0) && (
            <div className="border-b border-slate-100 px-5 py-3 text-[13px] text-slate-600">
              {report.newGroups.length > 0 ? (
                <p>
                  These will be created:{" "}
                  <span className="font-medium text-slate-900">{groupList(report.newGroups)}</span>
                </p>
              ) : (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span>
                    Not found: <span className="font-medium text-slate-900">{groupList(report.missingGroups)}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => toggleCreateGroups(true)}
                    disabled={busy}
                    className="font-medium text-accent-700 hover:text-accent-800"
                  >
                    Create them during import
                  </button>
                </div>
              )}
            </div>
          )}

          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-2.5">
            <label className="flex items-center gap-2 text-[13px] text-slate-600">
              <input
                type="checkbox"
                checked={problemsOnly}
                onChange={(e) => setProblemsOnly(e.target.checked)}
                className="size-4 rounded border-slate-300 accent-accent-600"
              />
              {report.mode === "update" ? "Hide unchanged rows" : "Show problems only"}
            </label>
            <span className="text-[12px] text-slate-400">Rows with problems are skipped</span>
          </div>

          <div className="max-h-[28rem] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="border-b border-slate-100 text-left text-[12px] text-slate-500">
                  <th className="w-14 px-5 py-2.5 font-medium">Row</th>
                  <th className="px-5 py-2.5 font-medium">Person</th>
                  <th className="px-5 py-2.5 font-medium">Role</th>
                  <th className="hidden px-5 py-2.5 font-medium md:table-cell">Placement</th>
                  <th className="px-5 py-2.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-[13px] text-slate-500">
                      {report.mode === "update" ? "Nothing changes and nothing has problems." : "No rows with problems."}
                    </td>
                  </tr>
                ) : (
                  rows.map((r) => (
                    <tr key={r.line} className={r.errors.length ? "bg-red-50/40" : undefined}>
                      <td className="px-5 py-3 text-slate-400 tabular-nums">{r.line}</td>
                      <td className="px-5 py-3">
                        <p className="font-medium text-slate-900">{r.name || <span className="text-slate-400">No name</span>}</p>
                        <p className="text-[13px] text-slate-500">{r.email || "—"}</p>
                      </td>
                      <td className="px-5 py-3 text-slate-700">{r.role ? roleMeta(r.role).label : "—"}</td>
                      <td className="hidden px-5 py-3 text-[13px] text-slate-700 md:table-cell">{r.placement || "—"}</td>
                      <td className="px-5 py-3">
                        {r.errors.length ? (
                          <ul className="space-y-0.5 text-[13px] text-red-700">
                            {r.errors.map((e) => (
                              <li key={e} className="flex gap-1.5">
                                <ExclamationTriangleIcon className="mt-0.5 size-3.5 shrink-0" />
                                {e}
                              </li>
                            ))}
                          </ul>
                        ) : report.mode === "update" ? (
                          r.changes.length ? (
                            <ul className="space-y-0.5 text-[13px] text-slate-700">
                              {r.changes.map((c) => (
                                <li key={c} className="flex gap-1.5">
                                  <CheckCircleIcon className="mt-0.5 size-3.5 shrink-0 text-emerald-600" />
                                  {c}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <span className="text-[13px] text-slate-500">No changes</span>
                          )
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-[13px] text-slate-700">
                            <CheckCircleIcon className="size-4 text-emerald-600" />
                            Ready{!r.passwordProvided && " · password generated"}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <CardFooter>
            <Button variant="secondary" onClick={reset} disabled={busy}>
              Choose another file
            </Button>
            {report.mode === "update" ? (
              <Button onClick={runImport} loading={busy} disabled={!report.summary.changing}>
                Update {report.summary.changing} user{report.summary.changing === 1 ? "" : "s"}
              </Button>
            ) : (
              <Button onClick={runImport} loading={busy} disabled={report.summary.valid === 0}>
                Import {report.summary.valid} user{report.summary.valid === 1 ? "" : "s"}
              </Button>
            )}
          </CardFooter>
        </Card>
      )}

      {step === 2 && (
        <Card className="max-w-2xl">
          <div className="space-y-5 p-6">
            <div className="flex items-start gap-3">
              <CheckCircleIcon className="mt-0.5 size-6 shrink-0 text-emerald-600" />
              <div>
                <p className="text-base font-semibold text-slate-900">
                  {result.mode === "update"
                    ? `Updated ${result.updated} user${result.updated === 1 ? "" : "s"}`
                    : `Imported ${result.created} user${result.created === 1 ? "" : "s"}`}
                </p>
                <p className="text-[13px] text-slate-500">
                  {result.mode === "update" && result.unchanged > 0 ? `${result.unchanged} had no changes. ` : ""}
                  {result.skipped > 0 ? `${result.skipped} row${result.skipped === 1 ? " was" : "s were"} skipped. ` : ""}
                  {result.groupsCreated.length > 0 && `Created ${groupList(result.groupsCreated)}. `}
                  {result.mode === "update"
                    ? "Anyone given a new password or role was signed out."
                    : "Everyone will choose their own password at first sign-in."}
                </p>
              </div>
            </div>

            {result.credentials?.length > 0 && (
              <div className="rounded-md border border-amber-200 bg-amber-50 p-4">
                <p className="text-sm font-medium text-amber-900">
                  {result.credentials.length} password{result.credentials.length === 1 ? " was" : "s were"} generated
                </p>
                <p className="mt-1 text-[13px] text-amber-800">
                  Download them now: they can't be shown again. Share each person's details privately.
                </p>
                <Button variant="secondary" className="mt-3" onClick={downloadCredentials}>
                  <ArrowDownTrayIcon className="size-4" />
                  Download sign-in details
                </Button>
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              <Link
                to="/users"
                className={buttonStyles()}
              >
                Go to users
              </Link>
              <Button variant="secondary" onClick={reset}>
                Import another file
              </Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
};

export default ImportUsers;
