import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import { CheckCircleIcon } from "@heroicons/react/20/solid";
import api from "../../../utils/axios";
import { useApi } from "../../../hooks/useApi";
import { Button, Card, CardFooter, CardHeader, Input, Kbd, Textarea } from "../../../components/ui";
import { inputStyles } from "../../../components/styles";
import { DifficultyBadge, OptionList, Segmented } from "../../../components/questions";
import { apiError, cx } from "../../../utils/helpers";
import { DIFFICULTIES, LETTERS } from "../../../utils/questions";

const EMPTY_QUESTION = { text: "", options: { A: "", B: "", C: "", D: "" }, correctAnswer: "", explanation: "" };

/** What's wrong with the form, as {field: message}. */
const problems = (form) => {
  const found = {};
  if (!form.subject.trim()) found.subject = "Enter a subject";
  if (!form.text.trim()) found.text = "Write the question";
  const filled = LETTERS.filter((l) => form.options[l].trim());
  if (filled.length < 4) found.options = "Fill in all four options";
  else if (new Set(LETTERS.map((l) => form.options[l].trim().toLowerCase())).size < 4) {
    found.options = "Each option must be different";
  }
  if (!found.options && !LETTERS.includes(form.correctAnswer)) found.options = "Choose the correct answer";
  return found;
};

/**
 * "Write your own": one question at a time. Subject, topic and difficulty stay
 * filled in after saving, so writing a set on one topic is quick.
 */
const WriteQuestion = () => {
  const [form, setForm] = useState({ subject: "", topic: "", difficulty: "medium", ...EMPTY_QUESTION });
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [added, setAdded] = useState([]); // saved this visit, newest first
  const questionRef = useRef(null);
  const bank = useApi("/questions", { limit: 1 }); // for the list of existing subjects

  const set = (patch) => {
    setForm((f) => ({ ...f, ...patch }));
    setErrors((e) => ({ ...e, ...Object.fromEntries(Object.keys(patch).map((k) => [k === "correctAnswer" ? "options" : k, undefined])) }));
  };
  const setOption = (letter, value) => {
    setForm((f) => ({ ...f, options: { ...f.options, [letter]: value } }));
    setErrors((e) => ({ ...e, options: undefined }));
  };

  const save = async (e) => {
    e?.preventDefault();
    const found = problems(form);
    if (Object.keys(found).length) {
      setErrors(found);
      document.getElementById(found.subject ? "write-subject" : found.text ? "write-text" : "write-option-A")?.focus();
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post("/questions", {
        questions: [
          {
            subject: form.subject.trim(),
            topic: form.topic.trim(),
            difficulty: form.difficulty,
            text: form.text.trim(),
            options: Object.fromEntries(LETTERS.map((l) => [l, form.options[l].trim()])),
            correctAnswer: form.correctAnswer,
            explanation: form.explanation.trim(),
            aiGenerated: false,
          },
        ],
      });
      setAdded((prev) => [data.questions[0], ...prev]);
      setForm((f) => ({ ...f, ...EMPTY_QUESTION }));
      toast.success("Question saved. Ready for the next one.");
      questionRef.current?.focus();
    } catch (err) {
      toast.error(apiError(err, "Couldn't save the question. Try again."));
    } finally {
      setSaving(false);
    }
  };

  const subjects = bank.data?.subjects ?? [];

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <Card>
        <form
          onSubmit={save}
          noValidate
          onKeyDown={(e) => (e.metaKey || e.ctrlKey) && e.key === "Enter" && save(e)}
        >
          <CardHeader title="New question" description="Multiple choice, four options, one correct answer." />
          <div className="space-y-5 p-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Input
                  id="write-subject"
                  label="Subject"
                  placeholder="e.g. Data structures"
                  maxLength={200}
                  list="write-subjects"
                  value={form.subject}
                  error={errors.subject}
                  onChange={(e) => set({ subject: e.target.value })}
                />
                <datalist id="write-subjects">
                  {subjects.map((s) => (
                    <option key={s} value={s} />
                  ))}
                </datalist>
              </div>
              <Input
                id="write-topic"
                label="Topic (optional)"
                placeholder="e.g. Linked lists"
                maxLength={120}
                value={form.topic}
                onChange={(e) => set({ topic: e.target.value })}
              />
            </div>
            <Segmented label="Difficulty" options={DIFFICULTIES} value={form.difficulty} onChange={(v) => set({ difficulty: v })} />
            <Textarea
              ref={questionRef}
              id="write-text"
              label="Question"
              rows={3}
              className="min-h-20"
              maxLength={2000}
              placeholder="e.g. Which data structure follows Last In, First Out?"
              value={form.text}
              error={errors.text}
              onChange={(e) => set({ text: e.target.value })}
            />
            <fieldset aria-describedby={errors.options ? "write-options-error" : undefined}>
              <legend className="mb-1.5 text-sm font-semibold text-slate-700">
                Options <span className="font-normal text-slate-500">(select the correct answer)</span>
              </legend>
              <div className="space-y-2">
                {LETTERS.map((letter) => (
                  <div
                    key={letter}
                    className={cx(
                      "flex items-center gap-2.5 rounded-md px-2 py-1 transition-colors",
                      form.correctAnswer === letter && "bg-emerald-50 ring-1 ring-emerald-300"
                    )}
                  >
                    <input
                      type="radio"
                      name="write-correct"
                      checked={form.correctAnswer === letter}
                      onChange={() => set({ correctAnswer: letter })}
                      aria-label={`Option ${letter} is the correct answer`}
                      className="size-4 accent-emerald-600"
                    />
                    <span className="w-4 font-mono text-[12px] text-slate-500">{letter}</span>
                    <input
                      id={`write-option-${letter}`}
                      value={form.options[letter]}
                      maxLength={500}
                      placeholder={`Option ${letter}`}
                      onChange={(e) => setOption(letter, e.target.value)}
                      aria-label={`Option ${letter}`}
                      className={cx(inputStyles(errors.options && !form.options[letter].trim()), "h-9 px-3")}
                    />
                  </div>
                ))}
              </div>
              {errors.options && (
                <p id="write-options-error" className="mt-1.5 text-[13px] text-red-600">
                  {errors.options}
                </p>
              )}
            </fieldset>
            <Textarea
              id="write-explanation"
              label="Explanation (optional)"
              rows={2}
              className="min-h-16"
              maxLength={2000}
              hint="Shown to students after the test closes, and after practice."
              value={form.explanation}
              onChange={(e) => set({ explanation: e.target.value })}
            />
          </div>
          <CardFooter>
            <p className="hidden text-[13px] text-slate-500 sm:block">
              <Kbd>Ctrl</Kbd> + <Kbd>Enter</Kbd> saves. Subject, topic and difficulty stay for the next question.
            </p>
            <Button type="submit" loading={saving}>
              Save question
            </Button>
          </CardFooter>
        </form>
      </Card>

      <Card className="lg:sticky lg:top-4">
        <CardHeader
          title="Added just now"
          description={added.length ? `${added.length} question${added.length === 1 ? "" : "s"} saved to the bank` : "Questions you save appear here."}
          action={
            added.length > 0 && (
              <Link to="/questions?mine=1" className="text-[13px] font-medium text-accent-700 hover:text-accent-800">
                Open bank
              </Link>
            )
          }
        />
        {added.length === 0 ? (
          <p className="px-5 py-8 text-center text-[13px] text-slate-500">Nothing yet.</p>
        ) : (
          <ol className="max-h-[36rem] divide-y divide-slate-100 overflow-auto">
            {added.map((q) => (
              <li key={q.id} className="space-y-2 px-5 py-3">
                <div className="flex items-start gap-2">
                  <CheckCircleIcon className="mt-0.5 size-4 shrink-0 text-emerald-600" />
                  <p className="text-[13px] font-medium text-slate-900">{q.text}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2 pl-6 text-[12px] text-slate-500">
                  <span>{q.subject}</span>
                  <DifficultyBadge value={q.difficulty} />
                </div>
                <div className="pl-6">
                  <OptionList options={q.options} correct={q.correctAnswer} compact />
                </div>
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
};

export default WriteQuestion;
