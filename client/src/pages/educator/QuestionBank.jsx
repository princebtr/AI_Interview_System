import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { PlusIcon, TrashIcon } from "@heroicons/react/20/solid";
import { RectangleStackIcon, SparklesIcon } from "@heroicons/react/24/outline";
import api from "../../utils/axios";
import { useAuth } from "../../context/AuthContext";
import { useApi } from "../../hooks/useApi";
import { Button, Card, PageHeader, SearchInput, Select } from "../../components/ui";
import { EmptyState, LoadError } from "../../components/data";
import { AiBadge, DifficultyBadge, OptionList } from "../../components/questions";
import { apiError, cx } from "../../utils/helpers";
import { DIFFICULTIES } from "../../utils/questions";
import { timeAgo } from "../../utils/time";

const PAGE_SIZE = 20;
const MAX_LIMIT = 200;

const QuestionBank = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [subject, setSubject] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [mine, setMine] = useState(false);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [pages, setPages] = useState(1);
  const [deleting, setDeleting] = useState(null);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => setPages(1), [subject, difficulty, mine, query]);

  const { data, loading, error, reload } = useApi("/questions", {
    limit: Math.min(MAX_LIMIT, PAGE_SIZE * pages),
    ...(subject && { subject }),
    ...(difficulty && { difficulty }),
    ...(mine && { mine: 1 }),
    ...(query && { q: query }),
  });

  const remove = async (question) => {
    if (!window.confirm("Delete this question from the bank? This can't be undone.")) return;
    setDeleting(question.id);
    try {
      await api.delete(`/questions/${question.id}`);
      toast.success("Question deleted");
      reload();
    } catch (err) {
      toast.error(apiError(err, "Couldn't delete the question."));
    } finally {
      setDeleting(null);
    }
  };

  const questions = data?.questions ?? [];
  const total = data?.total ?? 0;
  const filtered = Boolean(subject || difficulty || mine || query);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Teaching"
        title="Question bank"
        description="Reviewed, reusable questions for your institution. Everything here was checked by an educator before it was saved."
        actions={
          <Button onClick={() => navigate("/questions/add")}>
            <PlusIcon className="size-4" />
            Add questions
          </Button>
        }
      />

      <Card>
        <div className="flex flex-col gap-2 border-b border-slate-100 px-4 py-3 lg:flex-row lg:items-center">
          <SearchInput
            id="question-search"
            label="Search questions"
            className="flex-1"
            value={search}
            maxLength={100}
            placeholder="Search question text"
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="grid grid-cols-2 gap-2 sm:flex">
            <div className="sm:w-44">
              <label htmlFor="question-subject" className="sr-only">
                Subject
              </label>
              <Select id="question-subject" value={subject} onChange={(e) => setSubject(e.target.value)} compact>
                <option value="">All subjects</option>
                {(data?.subjects ?? []).map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </div>
            <div className="sm:w-36">
              <label htmlFor="question-difficulty" className="sr-only">
                Difficulty
              </label>
              <Select
                id="question-difficulty"
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value)}
                compact
              >
                <option value="">Any difficulty</option>
                {DIFFICULTIES.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </Select>
            </div>
            <label className="col-span-2 flex h-9 cursor-pointer items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700 shadow-xs transition-colors hover:border-slate-300 sm:col-span-1">
              <input
                type="checkbox"
                checked={mine}
                onChange={(e) => setMine(e.target.checked)}
                className="size-4 rounded border-slate-300 accent-accent-600"
              />
              Added by me
            </label>
          </div>
        </div>

        {error && !data ? (
          <div className="p-5">
            <LoadError onRetry={reload} />
          </div>
        ) : loading && !data ? (
          <ul className="divide-y divide-slate-100">
            {[0, 1, 2].map((i) => (
              <li key={i} className="space-y-3 px-5 py-4">
                <div className="h-3 w-40 animate-pulse rounded bg-slate-100" />
                <div className="h-4 w-3/4 animate-pulse rounded bg-slate-100" />
                <div className="h-16 animate-pulse rounded bg-slate-100" />
              </li>
            ))}
          </ul>
        ) : questions.length === 0 ? (
          <EmptyState
            icon={RectangleStackIcon}
            title={filtered ? "No questions match these filters" : "Your question bank is empty"}
            description={
              filtered
                ? "Try a different subject, difficulty or search."
                : "Generate questions with AI, write your own, or import a sheet of them."
            }
            action={
              !filtered && (
                <Button onClick={() => navigate("/questions/add")}>
                  <PlusIcon className="size-4" />
                  Add questions
                </Button>
              )
            }
          />
        ) : (
          <ul className={cx("divide-y divide-slate-100", loading && "opacity-60")}>
            {questions.map((q) => {
              const canDelete = user?.role === "admin" || q.createdBy?.id === user?.id;
              return (
                <li key={q.id} className="px-5 py-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5 text-[12px] text-slate-500">
                        <span className="font-medium text-slate-700">{q.subject}</span>
                        {q.topic && <span>· {q.topic}</span>}
                        <DifficultyBadge value={q.difficulty} />
                        {q.aiGenerated && <AiBadge />}
                      </div>
                      <p className="mt-1.5 text-sm leading-relaxed font-medium text-slate-900">{q.text}</p>
                    </div>
                    {canDelete && (
                      <button
                        type="button"
                        onClick={() => remove(q)}
                        disabled={deleting === q.id}
                        aria-label="Delete question"
                        title="Delete question"
                        className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                      >
                        <TrashIcon className="size-4" />
                      </button>
                    )}
                  </div>
                  <div className="mt-3">
                    <OptionList options={q.options} correct={q.correctAnswer} />
                  </div>
                  {q.explanation && (
                    <p className="mt-2.5 text-[13px] leading-relaxed text-slate-600">
                      <span className="font-medium text-slate-800">Why: </span>
                      {q.explanation}
                    </p>
                  )}
                  <p className="mt-2 text-[12px] text-slate-400">
                    Added by {q.createdBy?.name ?? "a former member"} · {timeAgo(q.createdAt)}
                  </p>
                </li>
              );
            })}
          </ul>
        )}

        {questions.length > 0 && (
          <div className="flex items-center justify-between gap-3 rounded-b-lg border-t border-slate-100 bg-slate-50/70 px-5 py-3 text-[13px] text-slate-500">
            <span className="tabular-nums">
              Showing {questions.length} of {total}
            </span>
            {questions.length < total && PAGE_SIZE * pages < MAX_LIMIT && (
              <Button variant="secondary" size="sm" loading={loading} onClick={() => setPages((p) => p + 1)}>
                Load more
              </Button>
            )}
          </div>
        )}
      </Card>
    </div>
  );
};

export default QuestionBank;
