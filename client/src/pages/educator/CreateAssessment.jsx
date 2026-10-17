import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import toast from "react-hot-toast";
import { CheckIcon } from "@heroicons/react/20/solid";
import { SparklesIcon } from "@heroicons/react/24/outline";
import api from "../../utils/axios";
import { useApi } from "../../hooks/useApi";
import { Button, Card, CardHeader, Field, Input, PageHeader, SearchInput, Select, Textarea } from "../../components/ui";
import { inputStyles } from "../../components/styles";
import { AiBadge, DifficultyBadge } from "../../components/questions";
import { MonitoringSettings } from "../../components/proctoring";
import { DEFAULT_MONITORING, monitoringFormValues } from "../../utils/proctoring";
import { apiError, cx } from "../../utils/helpers";
import { DIFFICULTIES } from "../../utils/questions";
import { formatClockTime, formatDateTime, formatDuration, toLocalInput } from "../../utils/time";

const DURATIONS = [15, 30, 45, 60, 90, 120];
const FIELDS = ["title", "cohortId", "startsAt", "durationMinutes", "marksPerQuestion", "numQuestions", "questionIds", "instructions"];

const nextQuarterHour = () => {
  const d = new Date(Date.now() + 60 * 60 * 1000);
  d.setMinutes(Math.ceil(d.getMinutes() / 15) * 15, 0, 0);
  return toLocalInput(d);
};

const clampInt = (value, low, high) => {
  const n = parseInt(value, 10);
  return Number.isNaN(n) ? "" : Math.max(low, Math.min(high, n));
};

const CreateAssessment = () => {
  const navigate = useNavigate();
  const cohorts = useApi("/institution/cohorts");
  const [form, setForm] = useState({
    title: "",
    cohortId: "",
    instructions: "",
    startsAt: nextQuarterHour(),
    durationMinutes: 45,
    numQuestions: 10,
    marksPerQuestion: 2,
    shuffleQuestions: true,
  });
  const [errors, setErrors] = useState({});
  const [selected, setSelected] = useState(() => new Map()); // id -> question
  const [subject, setSubject] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [saving, setSaving] = useState(false);
  const [monitoring, setMonitoring] = useState(DEFAULT_MONITORING);
  const capabilities = useApi("/proctoring/capabilities");

  // "Duplicate" on a test page opens /assessments/new?from=<id>: start from that
  // test's settings and questions (still in the bank), with a new start time.
  const [params] = useSearchParams();
  const from = params.get("from");
  const [copying, setCopying] = useState(Boolean(from));
  useEffect(() => {
    if (!from) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/assessments/${from}`);
        const source = data.assessment;
        const ids = source.questions.map((q) => q.id);
        const { data: found } = await api.get("/questions", { params: { ids: ids.join(","), limit: 200 } });
        if (cancelled) return;
        const byId = new Map(found.questions.map((q) => [q.id, q]));
        const kept = ids.filter((qid) => byId.has(qid));
        setForm((f) => ({
          ...f,
          title: `${source.title} (copy)`.slice(0, 200),
          cohortId: source.cohort.id,
          instructions: source.instructions ?? "",
          durationMinutes: source.durationMinutes,
          marksPerQuestion: source.marksPerQuestion,
          numQuestions: ids.length,
          shuffleQuestions: source.shuffleQuestions,
        }));
        if (source.monitoring) setMonitoring(monitoringFormValues(source.monitoring));
        setSelected(new Map(kept.map((qid) => [qid, byId.get(qid)])));
        const lost = ids.length - kept.length;
        toast.success(
          lost
            ? `Copied "${source.title}". ${lost} question${lost === 1 ? " is" : "s are"} no longer in the bank: pick replacements.`
            : `Copied "${source.title}". Choose a new start time.`
        );
      } catch (error) {
        if (!cancelled) toast.error(apiError(error, "Couldn't copy that test"));
      } finally {
        if (!cancelled) setCopying(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [from]);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const bank = useApi("/questions", {
    limit: 200,
    ...(subject && { subject }),
    ...(difficulty && { difficulty }),
    ...(query && { q: query }),
  });
  const questions = bank.data?.questions ?? [];
  const n = Number(form.numQuestions) || 0;

  const set = (key) => (e) => {
    const value = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((errs) => ({ ...errs, [key]: undefined }));
  };

  const toggle = (q) =>
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(q.id)) next.delete(q.id);
      else if (next.size < n) next.set(q.id, q);
      else toast.error(`This test has ${n} questions. Increase the number or unselect one first.`);
      return next;
    });

  // Fill the remaining slots at random from the questions currently listed.
  const pickRandom = () => {
    const pool = questions.filter((q) => !selected.has(q.id));
    for (let i = pool.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [pool[i], pool[j]] = [pool[j], pool[i]];
    }
    setSelected((prev) => {
      const next = new Map(prev);
      for (const q of pool) {
        if (next.size >= n) break;
        next.set(q.id, q);
      }
      return next;
    });
  };

  const startsAt = form.startsAt ? new Date(form.startsAt) : null;
  const endsAt = startsAt && form.durationMinutes ? new Date(startsAt.getTime() + form.durationMinutes * 60000) : null;
  const totalMarks = n * (Number(form.marksPerQuestion) || 0);
  const cohort = cohorts.data?.cohorts?.find((c) => c.id === form.cohortId);

  // What still stops the test from being scheduled (cheap, so worked out on every render).
  const missing = [];
  if (form.title.trim().length < 3) missing.push("Add a title");
  if (!form.cohortId) missing.push("Choose a cohort");
  if (!startsAt || startsAt.getTime() < Date.now() - 5 * 60000) missing.push("Pick a start time in the future");
  if (!(form.durationMinutes >= 5 && form.durationMinutes <= 300)) missing.push("Set a duration of 5-300 minutes");
  if (!(n >= 1 && n <= 100)) missing.push("Set 1-100 questions");
  if (!(form.marksPerQuestion >= 1 && form.marksPerQuestion <= 100)) missing.push("Set 1-100 marks per question");
  const gap = n - selected.size;
  if (n >= 1 && gap > 0) missing.push(`Select ${gap} more question${gap === 1 ? "" : "s"}`);
  if (n >= 1 && gap < 0) missing.push(`Unselect ${-gap} question${gap === -1 ? "" : "s"}`);

  const submit = async () => {
    setSaving(true);
    setErrors({});
    try {
      const { data } = await api.post("/assessments", {
        title: form.title.trim(),
        cohortId: form.cohortId,
        instructions: form.instructions.trim(),
        subject: subject || [...selected.values()][0]?.subject || "",
        startsAt: new Date(form.startsAt).toISOString(),
        durationMinutes: Number(form.durationMinutes),
        marksPerQuestion: Number(form.marksPerQuestion),
        numQuestions: n,
        questionIds: [...selected.keys()],
        shuffleQuestions: form.shuffleQuestions,
        monitoring: {
          ...monitoring,
          // Unavailable on this server: don't ask for it.
          cameraRequired: monitoring.cameraRequired && capabilities.data?.cameraChecks !== false,
        },
      });
      toast.success(`Scheduled for ${data.assessment.cohort.name}`);
      navigate(`/assessments/${data.assessment.id}`);
    } catch (error) {
      const all = error.response?.data?.errors ?? [];
      const fieldErrors = all.filter((e) => FIELDS.includes(e.field));
      const monitoringError = all.find((e) => e.field?.startsWith("monitoring"));
      if (monitoringError && !fieldErrors.length) {
        toast.error(`Proctoring: ${monitoringError.message}`);
      } else if (fieldErrors.length) {
        setErrors(Object.fromEntries(fieldErrors.map((e) => [e.field, e.message])));
        toast.error(fieldErrors[0].message);
      } else {
        toast.error(apiError(error, "Couldn't schedule the test. Try again."));
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Tests"
        title={from ? "Duplicate a test" : "Create a test"}
        description={
          copying
            ? "Copying the test's settings and questions…"
            : "Choose questions from your question bank, schedule the test and assign it to a cohort."
        }
      />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-6">
          <Card>
            <CardHeader title="Details" />
            <div className="grid gap-5 p-5 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <Input id="test-title" label="Title" placeholder="e.g. Java Fundamentals, Unit 3" maxLength={200} value={form.title} error={errors.title} onChange={set("title")} />
              </div>
              <Select id="test-cohort" label="Cohort" value={form.cohortId} error={errors.cohortId} onChange={set("cohortId")}>
                <option value="">Choose a cohort</option>
                {(cohorts.data?.cohorts ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.studentCount} student{c.studentCount === 1 ? "" : "s"})
                  </option>
                ))}
              </Select>
              <div className="sm:col-span-2">
                <Textarea
                  id="test-instructions"
                  label="Instructions (optional)"
                  rows={3}
                  className="min-h-20"
                  placeholder="Shown to students before they start."
                  maxLength={2000}
                  value={form.instructions}
                  error={errors.instructions}
                  onChange={set("instructions")}
                />
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader title="Schedule" description="The test opens at the start time and closes for everyone when the duration ends." />
            <div className="grid gap-5 p-5 sm:grid-cols-2">
              <Input
                id="test-start"
                label="Starts"
                type="datetime-local"
                min={toLocalInput(new Date())}
                value={form.startsAt}
                error={errors.startsAt}
                hint={endsAt ? `Closes ${formatDateTime(endsAt)}` : undefined}
                onChange={set("startsAt")}
                action={
                  <button
                    type="button"
                    onClick={() => {
                      setForm((f) => ({ ...f, startsAt: toLocalInput(new Date()) }));
                      setErrors((errs) => ({ ...errs, startsAt: undefined }));
                    }}
                    className="text-[13px] font-medium text-accent-700 hover:text-accent-800"
                  >
                    Start now
                  </button>
                }
              />
              <Field id="test-duration" label="Duration (minutes)" error={errors.durationMinutes}>
                <div className="space-y-2">
                  <input
                    id="test-duration"
                    type="number"
                    aria-invalid={errors.durationMinutes ? true : undefined}
                    aria-describedby={errors.durationMinutes ? "test-duration-error" : undefined}
                    min={5}
                    max={300}
                    value={form.durationMinutes}
                    onChange={(e) => setForm((f) => ({ ...f, durationMinutes: clampInt(e.target.value, 1, 300) }))}
                    className={cx(inputStyles(errors.durationMinutes), "h-10 px-3")}
                  />
                  <div className="flex flex-wrap gap-1.5">
                    {DURATIONS.map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setForm((f) => ({ ...f, durationMinutes: m }))}
                        aria-pressed={form.durationMinutes === m}
                        className={cx(
                          "rounded-full border px-2.5 py-0.5 text-[12px] transition-colors",
                          form.durationMinutes === m
                            ? "border-accent-600 bg-accent-50 text-accent-800"
                            : "border-slate-200 text-slate-600 hover:border-slate-300"
                        )}
                      >
                        {formatDuration(m)}
                      </button>
                    ))}
                  </div>
                </div>
              </Field>
            </div>
          </Card>

          <Card>
            <CardHeader title="Marking" />
            <div className="grid gap-5 p-5 sm:grid-cols-2">
              <Input
                id="test-count"
                label="Number of questions"
                type="number"
                min={1}
                max={100}
                value={form.numQuestions}
                error={errors.numQuestions}
                onChange={(e) => setForm((f) => ({ ...f, numQuestions: clampInt(e.target.value, 1, 100) }))}
              />
              <Input
                id="test-marks"
                label="Marks per question"
                type="number"
                min={1}
                max={100}
                value={form.marksPerQuestion}
                error={errors.marksPerQuestion}
                hint={totalMarks ? `Total: ${totalMarks} marks` : undefined}
                onChange={(e) => setForm((f) => ({ ...f, marksPerQuestion: clampInt(e.target.value, 1, 100) }))}
              />
              <label className="flex items-start gap-2.5 text-sm text-slate-700 sm:col-span-2">
                <input type="checkbox" checked={form.shuffleQuestions} onChange={set("shuffleQuestions")} className="mt-0.5 size-4 rounded border-slate-300 accent-accent-700" />
                <span>
                  Shuffle the question order for each student
                  <span className="block text-[13px] text-slate-500">Makes it harder to share answers during the test.</span>
                </span>
              </label>
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Proctoring"
              description="Full screen, camera and microphone checks while students sit the test. You can change them until the first student starts."
            />
            <div className="p-5">
              <MonitoringSettings value={monitoring} onChange={setMonitoring} capabilities={capabilities.data} />
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Questions"
              description={`${selected.size} of ${n || 0} selected`}
              action={
                <div className="flex gap-2">
                  {selected.size > 0 && (
                    <Button variant="ghost" size="sm" onClick={() => setSelected(new Map())}>
                      Clear
                    </Button>
                  )}
                  {gap > 0 && (
                    <Button variant="secondary" size="sm" onClick={pickRandom} disabled={!questions.length}>
                      Pick {gap} at random
                    </Button>
                  )}
                </div>
              }
            />
            <div className="grid gap-2 border-b border-slate-100 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_170px_150px]">
              <SearchInput
                id="pick-search"
                label="Search questions"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search questions"
              />
              <div>
                <label htmlFor="pick-subject" className="sr-only">Subject</label>
                <Select id="pick-subject" value={subject} onChange={(e) => setSubject(e.target.value)} compact>
                  <option value="">All subjects</option>
                  {(bank.data?.subjects ?? []).map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </Select>
              </div>
              <div>
                <label htmlFor="pick-difficulty" className="sr-only">Difficulty</label>
                <Select id="pick-difficulty" value={difficulty} onChange={(e) => setDifficulty(e.target.value)} compact>
                  <option value="">Any difficulty</option>
                  {DIFFICULTIES.map((d) => (
                    <option key={d.value} value={d.value}>{d.label}</option>
                  ))}
                </Select>
              </div>
            </div>

            {errors.questionIds && <p className="px-5 pt-3 text-[13px] text-red-600">{errors.questionIds}</p>}

            {bank.data && bank.data.total < n && !query && !difficulty && (
              <div className="mx-5 mt-4 flex flex-col gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-900 sm:flex-row sm:items-center sm:justify-between">
                <span>
                  {bank.data.total} question{bank.data.total === 1 ? "" : "s"} available{subject ? ` in ${subject}` : ""}, but the test needs {n}.
                </span>
                <Link to="/generator" className="inline-flex items-center gap-1 font-medium text-amber-900 underline underline-offset-2">
                  <SparklesIcon className="size-4" />
                  Generate more with AI
                </Link>
              </div>
            )}

            <ul className="max-h-[32rem] divide-y divide-slate-100 overflow-y-auto">
              {bank.loading && !bank.data ? (
                <li className="px-5 py-8 text-center text-[13px] text-slate-500">Loading your question bank…</li>
              ) : questions.length === 0 ? (
                <li className="px-5 py-8 text-center text-[13px] text-slate-500">
                  No questions match.{" "}
                  <Link to="/generator" className="font-medium text-accent-700 hover:text-accent-800">
                    Generate some with AI
                  </Link>
                </li>
              ) : (
                questions.map((q) => {
                  const checked = selected.has(q.id);
                  return (
                    <li key={q.id}>
                      <label className={cx("flex cursor-pointer gap-3 px-5 py-3 transition-colors", checked ? "bg-accent-50/50" : "hover:bg-slate-50")}>
                        <input type="checkbox" checked={checked} onChange={() => toggle(q)} className="mt-1 size-4 shrink-0 rounded border-slate-300 accent-accent-700" />
                        <span className="min-w-0">
                          <span className="block text-sm text-slate-900">{q.text}</span>
                          <span className="mt-1 flex flex-wrap items-center gap-1.5 text-[12px] text-slate-500">
                            <span className="font-medium text-slate-600">{q.subject}</span>
                            <DifficultyBadge value={q.difficulty} />
                            {q.aiGenerated && <AiBadge />}
                            <span>· Answer {q.correctAnswer}</span>
                          </span>
                        </span>
                      </label>
                    </li>
                  );
                })
              )}
            </ul>
          </Card>
        </div>

        <Card className="h-fit lg:sticky lg:top-10">
          <CardHeader title="Summary" />
          <dl className="space-y-3 px-5 py-4 text-sm">
            {[
              ["Test", form.title.trim() || "Untitled"],
              ["Cohort", cohort?.name ?? "Not chosen"],
              ["Opens", startsAt ? formatDateTime(startsAt) : "Not set"],
              ["Closes", endsAt ? formatClockTime(endsAt) : "Not set"],
              ["Questions", `${selected.size} / ${n || 0}`],
              ["Total marks", totalMarks || "-"],
              ["Proctoring", "On"],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between gap-4">
                <dt className="text-slate-500">{label}</dt>
                <dd className="truncate text-right font-medium text-slate-900">{value}</dd>
              </div>
            ))}
          </dl>
          <div className="space-y-3 rounded-b-lg border-t border-slate-100 bg-slate-50/70 px-5 py-4">
            {missing.length > 0 ? (
              <ul className="space-y-1 text-[13px] text-slate-500">
                {missing.map((m) => (
                  <li key={m}>· {m}</li>
                ))}
              </ul>
            ) : (
              <p className="flex items-center gap-1.5 text-[13px] text-emerald-700">
                <CheckIcon className="size-4" />
                Ready to schedule
              </p>
            )}
            <Button className="w-full" onClick={submit} loading={saving} disabled={missing.length > 0}>
              Schedule test
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default CreateAssessment;
