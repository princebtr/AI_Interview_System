import { useState } from "react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import {
  ArrowPathIcon,
  CheckIcon,
  ExclamationTriangleIcon,
  PencilSquareIcon,
  TrashIcon,
} from "@heroicons/react/20/solid";
import { SparklesIcon } from "@heroicons/react/24/outline";
import api from "../../utils/axios";
import { Button, Card, CardFooter, CardHeader, ChoiceChips, Input, PageHeader, Textarea } from "../../components/ui";
import { inputStyles } from "../../components/styles";
import { OptionList } from "../../components/questions";
import { apiError, cx } from "../../utils/helpers";
import { DIFFICULTIES, LETTERS } from "../../utils/questions";

const COUNTS = [5, 10, 15, 20];
const SUGGESTED = ["Data structures", "Java", "Python", "DBMS", "Operating systems", "Computer networks"];

let draftId = 0;
const toDraft = (q) => ({
  key: ++draftId,
  text: q.question,
  options: { ...q.options },
  correctAnswer: q.correctAnswer,
  explanation: q.explanation ?? "",
  approved: false,
  editing: false,
  busy: false,
});

const draftProblem = (d) => {
  if (!d.text.trim()) return "Add the question text.";
  if (LETTERS.some((l) => !d.options[l]?.trim())) return "Fill in all four options.";
  if (!LETTERS.includes(d.correctAnswer)) return "Choose the correct answer.";
  return null;
};

const Segmented = ({ label, options, value, onChange }) => (
  <fieldset>
    <legend className="mb-1.5 text-sm font-medium text-slate-800">{label}</legend>
    <div className="inline-flex rounded-md border border-slate-200 bg-slate-100 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            "h-8 min-w-12 rounded px-3 text-sm font-medium tabular-nums transition-colors",
            value === o.value
              ? "bg-white text-slate-900 shadow-xs ring-1 ring-slate-200"
              : "text-slate-500 hover:text-slate-800"
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  </fieldset>
);

const DraftEditor = ({ draft, onChange, onDone }) => {
  const problem = draftProblem(draft);
  const setOption = (letter, value) => onChange({ options: { ...draft.options, [letter]: value } });
  return (
    <div className="space-y-4">
      <Textarea
        id={`draft-${draft.key}-text`}
        label="Question"
        rows={3}
        className="min-h-20"
        value={draft.text}
        onChange={(e) => onChange({ text: e.target.value })}
      />
      <fieldset>
        <legend className="mb-1.5 text-sm font-medium text-slate-800">Options (select the correct answer)</legend>
        <div className="space-y-2">
          {LETTERS.map((letter) => (
            <div key={letter} className="flex items-center gap-2.5">
              <input
                type="radio"
                name={`draft-${draft.key}-correct`}
                checked={draft.correctAnswer === letter}
                onChange={() => onChange({ correctAnswer: letter })}
                aria-label={`Option ${letter} is correct`}
                className="size-4"
              />
              <span className="w-4 font-mono text-[12px] text-slate-500">{letter}</span>
              <input
                value={draft.options[letter] ?? ""}
                onChange={(e) => setOption(letter, e.target.value)}
                aria-label={`Option ${letter}`}
                className={cx(inputStyles(), "h-9 px-3")}
              />
            </div>
          ))}
        </div>
      </fieldset>
      <Textarea
        id={`draft-${draft.key}-explanation`}
        label="Explanation (optional)"
        rows={2}
        className="min-h-16"
        value={draft.explanation}
        onChange={(e) => onChange({ explanation: e.target.value })}
      />
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] text-red-600">{problem}</p>
        <Button size="sm" onClick={onDone} disabled={Boolean(problem)}>
          Done editing
        </Button>
      </div>
    </div>
  );
};

const Generator = () => {
  const navigate = useNavigate();
  const [subject, setSubject] = useState("");
  const [topics, setTopics] = useState("");
  const [difficulty, setDifficulty] = useState("medium");
  const [count, setCount] = useState(10);
  const [subjectError, setSubjectError] = useState("");
  const [drafts, setDrafts] = useState([]);
  const [settings, setSettings] = useState(null); // what the current drafts were generated with
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);

  const request = (params, numQuestions) =>
    api.post(
      "/ai/generate-mcq-questions",
      {
        subject: params.subject,
        numQuestions,
        difficulty: params.difficulty,
        ...(params.topics && { topics: params.topics }),
      },
      { timeout: 60000 }
    );

  const generate = async (e) => {
    e.preventDefault();
    const params = { subject: subject.trim(), topics: topics.trim(), difficulty };
    if (!params.subject) {
      setSubjectError("Enter a subject.");
      return;
    }
    setSubjectError("");
    setGenerating(true);
    try {
      const { data } = await request(params, count);
      setDrafts(data.questions.map(toDraft));
      setSettings(params);
    } catch (err) {
      toast.error(apiError(err, "Couldn't generate questions. Try again."));
    } finally {
      setGenerating(false);
    }
  };

  const update = (key, patch) => setDrafts((all) => all.map((d) => (d.key === key ? { ...d, ...patch } : d)));
  const remove = (key) => setDrafts((all) => all.filter((d) => d.key !== key));

  const regenerate = async (key) => {
    update(key, { busy: true });
    try {
      const { data } = await request(settings, 1);
      const fresh = toDraft(data.questions[0]);
      setDrafts((all) => all.map((d) => (d.key === key ? fresh : d)));
    } catch (err) {
      update(key, { busy: false });
      toast.error(apiError(err, "Couldn't regenerate that question."));
    }
  };

  const approvable = drafts.filter((d) => !d.editing && !draftProblem(d));
  const approved = drafts.filter((d) => d.approved);

  const approveAll = () =>
    setDrafts((all) => all.map((d) => (!d.editing && !draftProblem(d) ? { ...d, approved: true } : d)));

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.post("/questions", {
        questions: approved.map((d) => ({
          text: d.text.trim(),
          options: Object.fromEntries(LETTERS.map((l) => [l, d.options[l].trim()])),
          correctAnswer: d.correctAnswer,
          explanation: d.explanation.trim(),
          subject: settings.subject,
          topic: settings.topics,
          difficulty: settings.difficulty,
          aiGenerated: true,
        })),
      });
      toast.success(`Saved ${data.created} question${data.created === 1 ? "" : "s"} to the bank`);
      navigate("/questions");
    } catch (err) {
      toast.error(apiError(err, "Couldn't save the questions. Try again."));
    } finally {
      setSaving(false);
    }
  };

  const startOver = () => {
    if (drafts.length && !window.confirm("Discard these generated questions?")) return;
    setDrafts([]);
    setSettings(null);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Teaching"
        title="AI question generator"
        description="Generate multiple-choice questions, review every one, then save the approved set to your question bank."
      />

      {!settings ? (
        <Card className="max-w-3xl">
          <CardHeader title="What should the questions cover?" />
          <form onSubmit={generate} noValidate>
            <div className="space-y-6 p-5">
              <div className="space-y-3">
                <Input
                  id="gen-subject"
                  label="Subject"
                  placeholder="e.g. Data structures"
                  maxLength={200}
                  value={subject}
                  error={subjectError}
                  onChange={(e) => setSubject(e.target.value)}
                />
                <ChoiceChips options={SUGGESTED} value={subject} onChange={setSubject} />
              </div>
              <Input
                id="gen-topics"
                label="Topics (optional)"
                placeholder="e.g. Arrays, linked lists, trees"
                hint="Separate topics with commas to focus the questions."
                maxLength={120}
                value={topics}
                onChange={(e) => setTopics(e.target.value)}
              />
              <div className="flex flex-wrap gap-6">
                <Segmented label="Difficulty" options={DIFFICULTIES} value={difficulty} onChange={setDifficulty} />
                <Segmented
                  label="Questions"
                  options={COUNTS.map((n) => ({ value: n, label: String(n) }))}
                  value={count}
                  onChange={setCount}
                />
              </div>
            </div>
            <CardFooter>
              <p className="text-[13px] text-slate-500">Nothing is saved until you approve it.</p>
              <Button type="submit" loading={generating}>
                <SparklesIcon className="size-4" />
                {generating ? `Generating ${count} questions` : "Generate questions"}
              </Button>
            </CardFooter>
          </form>
        </Card>
      ) : (
        <>
          <Card className="flex flex-col gap-3 px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-slate-700">
              <span className="font-medium text-slate-900">{settings.subject}</span>
              {settings.topics && <span className="text-slate-500"> · {settings.topics}</span>}
              <span className="text-slate-500 capitalize"> · {settings.difficulty}</span>
              <span className="text-slate-500"> · {drafts.length} question{drafts.length === 1 ? "" : "s"}</span>
            </p>
            <Button variant="secondary" size="sm" onClick={startOver}>
              Start over
            </Button>
          </Card>

          <div className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-900">
            <ExclamationTriangleIcon className="mt-0.5 size-4 shrink-0 text-amber-600" />
            <p>
              AI can get facts and answer keys wrong. Check each question and its correct answer, then
              approve it. Only approved questions are saved.
            </p>
          </div>

          {drafts.length === 0 ? (
            <Card className="p-8 text-center text-sm text-slate-500">
              You removed every question.{" "}
              <button type="button" onClick={startOver} className="font-medium text-accent-700 hover:text-accent-800">
                Generate a new set
              </button>
            </Card>
          ) : (
            <ol className="space-y-3">
              {drafts.map((d, i) => (
                <li key={d.key}>
                  <Card className={cx("transition-colors", d.approved && "border-emerald-300")}>
                    <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-2.5">
                      <span className="text-[13px] font-medium text-slate-500 tabular-nums">Question {i + 1}</span>
                      <div className="flex items-center gap-1">
                        {!d.editing && (
                          <>
                            <Button variant="ghost" size="sm" onClick={() => update(d.key, { editing: true, approved: false })} disabled={d.busy}>
                              <PencilSquareIcon className="size-4" />
                              Edit
                            </Button>
                            <Button variant="ghost" size="sm" onClick={() => regenerate(d.key)} loading={d.busy}>
                              {!d.busy && <ArrowPathIcon className="size-4" />}
                              Regenerate
                            </Button>
                          </>
                        )}
                        <Button variant="ghost" size="sm" onClick={() => remove(d.key)} disabled={d.busy} aria-label={`Remove question ${i + 1}`}>
                          <TrashIcon className="size-4" />
                        </Button>
                      </div>
                    </div>
                    <div className={cx("p-5", d.busy && "opacity-50")}>
                      {d.editing ? (
                        <DraftEditor
                          draft={d}
                          onChange={(patch) => update(d.key, patch)}
                          onDone={() => update(d.key, { editing: false })}
                        />
                      ) : (
                        <>
                          <p className="text-sm leading-relaxed font-medium text-slate-900">{d.text}</p>
                          <div className="mt-3">
                            <OptionList options={d.options} correct={d.correctAnswer} />
                          </div>
                          {d.explanation && (
                            <p className="mt-2.5 text-[13px] leading-relaxed text-slate-600">
                              <span className="font-medium text-slate-800">Why: </span>
                              {d.explanation}
                            </p>
                          )}
                        </>
                      )}
                    </div>
                    {!d.editing && (
                      <div className="flex justify-end rounded-b-lg border-t border-slate-100 bg-slate-50/70 px-5 py-2.5">
                        <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
                          <input
                            type="checkbox"
                            checked={d.approved}
                            disabled={d.busy || Boolean(draftProblem(d))}
                            onChange={(e) => update(d.key, { approved: e.target.checked })}
                            className="size-4 rounded border-slate-300"
                          />
                          Approved
                        </label>
                      </div>
                    )}
                  </Card>
                </li>
              ))}
            </ol>
          )}

          {drafts.length > 0 && (
            <div className="sticky bottom-4 z-10">
              <Card className="flex flex-col gap-3 px-5 py-3 shadow-lg sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-slate-700 tabular-nums">
                  <span className="font-semibold text-slate-900">{approved.length}</span> of {drafts.length} approved
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    onClick={approveAll}
                    disabled={approvable.every((d) => d.approved)}
                  >
                    <CheckIcon className="size-4" />
                    Approve all
                  </Button>
                  <Button onClick={save} loading={saving} disabled={approved.length === 0}>
                    Save {approved.length || ""} to question bank
                  </Button>
                </div>
              </Card>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default Generator;
