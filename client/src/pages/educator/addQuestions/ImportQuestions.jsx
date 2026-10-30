import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import {
  ArrowDownTrayIcon,
  CheckCircleIcon,
  DocumentArrowUpIcon,
  ExclamationTriangleIcon,
} from "@heroicons/react/20/solid";
import api from "../../../utils/axios";
import { Badge, Button, Card, CardFooter, CardHeader, Input } from "../../../components/ui";
import { buttonStyles } from "../../../components/styles";
import { DifficultyBadge } from "../../../components/questions";
import { apiError, cx } from "../../../utils/helpers";

const MAX_BYTES = 1024 * 1024;
const SAMPLE = "/sample-questions.csv"; // client/public/sample-questions.csv

const COLUMNS = [
  ["subject", "Required, unless you set a default subject below."],
  ["topic", "Optional."],
  ["difficulty", "easy, medium or hard. Blank means medium."],
  ["question", "Required. The question text."],
  ["option_a … option_d", "Required. The four options."],
  ["correct_answer", "A, B, C or D, or the exact text of the correct option."],
  ["explanation", "Optional. Shown after the test closes."],
];

const Steps = ({ current }) => (
  <ol className="flex items-center gap-2 text-[13px]" aria-label="Import progress">
    {["Upload", "Review", "Done"].map((label, i) => (
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
        {i < 2 && <span className="mx-1 h-px w-6 bg-slate-200" aria-hidden="true" />}
      </li>
    ))}
  </ol>
);

/** "Import from a sheet": upload a CSV, see every row checked, then import the valid ones. */
const ImportQuestions = () => {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [subject, setSubject] = useState("");
  const [report, setReport] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [problemsOnly, setProblemsOnly] = useState(false);

  const send = async (chosen, commit) => {
    const form = new FormData();
    form.append("file", chosen);
    form.append("commit", commit ? "true" : "false");
    if (subject.trim()) form.append("subject", subject.trim());
    const { data } = await api.post("/questions/import", form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 120000,
    });
    return data;
  };

  const check = async (chosen) => {
    if (!chosen) return;
    if (!/\.csv$/i.test(chosen.name)) {
      toast.error("Choose a .csv file. In Excel or Google Sheets, use File → Download / Save As → CSV.");
      return;
    }
    if (chosen.size > MAX_BYTES) {
      toast.error("That file is larger than 1 MB. Split it into smaller files.");
      return;
    }
    setBusy(true);
    try {
      const data = await send(chosen, false);
      setFile(chosen);
      setReport(data);
      setProblemsOnly(data.summary.invalid > 0);
    } catch (err) {
      toast.error(apiError(err, "Couldn't read that file."));
      if (inputRef.current) inputRef.current.value = "";
    } finally {
      setBusy(false);
    }
  };

  const runImport = async () => {
    setBusy(true);
    try {
      const data = await send(file, true);
      setResult(data);
      toast.success(`Imported ${data.created} question${data.created === 1 ? "" : "s"}`);
    } catch (err) {
      toast.error(apiError(err, "The import failed. Nothing was imported."));
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

  const step = result ? 2 : report ? 1 : 0;
  const rows = report ? (problemsOnly ? report.rows.filter((r) => r.errors.length) : report.rows) : [];

  return (
    <div className="space-y-6">
      <Steps current={step} />

      {step === 0 && (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader title="Upload a CSV file" description="Up to 500 questions and 1 MB per file. Nothing is saved until you confirm." />
            <div className="space-y-5 p-5">
              <label
                htmlFor="questions-file"
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  check(e.dataTransfer.files?.[0]);
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
                <span className="mt-1 text-[13px] text-slate-500">Export it from Excel or Google Sheets as CSV</span>
                <input
                  ref={inputRef}
                  id="questions-file"
                  type="file"
                  accept=".csv,text/csv"
                  className="sr-only"
                  disabled={busy}
                  onChange={(e) => check(e.target.files?.[0])}
                />
              </label>
              <Input
                id="import-subject"
                label="Default subject (optional)"
                placeholder="e.g. Data structures"
                maxLength={200}
                hint="Used for rows whose subject cell is empty. Then your sheet doesn't need a subject column."
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
              />
            </div>
          </Card>

          <Card>
            <CardHeader title="Sheet format" description="One question per row, with a header row first." />
            <div className="space-y-4 p-5">
              <dl className="space-y-2 text-[13px]">
                {COLUMNS.map(([name, help]) => (
                  <div key={name}>
                    <dt className="font-mono text-[12px] font-medium text-slate-800">{name}</dt>
                    <dd className="text-slate-500">{help}</dd>
                  </div>
                ))}
              </dl>
              <p className="text-[12px] text-slate-500">
                Short headers work too: <span className="font-mono">Question, A, B, C, D, Answer</span>.
              </p>
              <a href={SAMPLE} download className={buttonStyles({ variant: "secondary" })}>
                <ArrowDownTrayIcon className="size-4" />
                Download sample CSV
              </a>
            </div>
          </Card>
        </div>
      )}

      {step === 1 && (
        <Card>
          <CardHeader
            title={file?.name ?? "Review"}
            description={`${report.summary.total} row${report.summary.total === 1 ? "" : "s"} checked`}
            action={
              <div className="flex flex-wrap justify-end gap-2">
                <Badge tone="success">{report.summary.valid} ready</Badge>
                {report.summary.invalid > 0 && <Badge tone="danger">{report.summary.invalid} with problems</Badge>}
              </div>
            }
          />
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-2.5">
            <label className="flex items-center gap-2 text-[13px] text-slate-600">
              <input
                type="checkbox"
                checked={problemsOnly}
                onChange={(e) => setProblemsOnly(e.target.checked)}
                className="size-4 rounded border-slate-300 accent-accent-600"
              />
              Show problems only
            </label>
            <span className="text-[12px] text-slate-400">Rows with problems are skipped</span>
          </div>
          <div className="max-h-[32rem] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="border-b border-slate-100 text-left text-[12px] text-slate-500">
                  <th className="w-14 px-5 py-2.5 font-medium">Row</th>
                  <th className="px-5 py-2.5 font-medium">Question</th>
                  <th className="hidden px-5 py-2.5 font-medium md:table-cell">Subject</th>
                  <th className="w-20 px-5 py-2.5 font-medium">Answer</th>
                  <th className="px-5 py-2.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-[13px] text-slate-500">
                      No rows with problems.
                    </td>
                  </tr>
                ) : (
                  rows.map((r) => (
                    <tr key={r.line} className={r.errors.length ? "bg-red-50/40" : undefined}>
                      <td className="px-5 py-3 align-top text-slate-400 tabular-nums">{r.line}</td>
                      <td className="max-w-md px-5 py-3 align-top">
                        <p className="line-clamp-2 text-slate-900">{r.text || <span className="text-slate-400">No question</span>}</p>
                        {r.correctAnswer && r.options?.[r.correctAnswer] && (
                          <p className="mt-0.5 truncate text-[12px] text-emerald-700">✓ {r.options[r.correctAnswer]}</p>
                        )}
                      </td>
                      <td className="hidden px-5 py-3 align-top md:table-cell">
                        <p className="text-slate-700">{r.subject || "—"}</p>
                        <div className="mt-1">
                          <DifficultyBadge value={["easy", "medium", "hard"].includes(r.difficulty) ? r.difficulty : null} />
                        </div>
                      </td>
                      <td className="px-5 py-3 align-top font-mono text-slate-700">{r.correctAnswer ?? "—"}</td>
                      <td className="px-5 py-3 align-top">
                        {r.errors.length ? (
                          <ul className="space-y-0.5 text-[13px] text-red-700">
                            {r.errors.map((e) => (
                              <li key={e} className="flex gap-1.5">
                                <ExclamationTriangleIcon className="mt-0.5 size-3.5 shrink-0" />
                                {e}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-[13px] text-slate-700">
                            <CheckCircleIcon className="size-4 text-emerald-600" />
                            Ready
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
            <Button onClick={runImport} loading={busy} disabled={report.summary.valid === 0}>
              Import {report.summary.valid} question{report.summary.valid === 1 ? "" : "s"}
            </Button>
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
                  Imported {result.created} question{result.created === 1 ? "" : "s"}
                </p>
                <p className="text-[13px] text-slate-500">
                  {result.subjects.join(", ")}
                  {result.skipped > 0 &&
                    ` · ${result.skipped} row${result.skipped === 1 ? " was" : "s were"} skipped`}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link to="/questions?mine=1" className={buttonStyles()}>
                Open question bank
              </Link>
              <Link to="/assessments/new" className={buttonStyles({ variant: "secondary" })}>
                Create a test
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

export default ImportQuestions;
