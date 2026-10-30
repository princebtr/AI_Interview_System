import { Link, useSearchParams } from "react-router-dom";
import { PencilSquareIcon, SparklesIcon, TableCellsIcon } from "@heroicons/react/24/outline";
import { PageHeader } from "../../components/ui";
import { buttonStyles } from "../../components/styles";
import { cx } from "../../utils/helpers";
import AiGenerator from "./addQuestions/AiGenerator";
import WriteQuestion from "./addQuestions/WriteQuestion";
import ImportQuestions from "./addQuestions/ImportQuestions";

const METHODS = [
  {
    value: "ai",
    label: "Generate with AI",
    description: "Describe a subject; review and approve what AI drafts.",
    icon: SparklesIcon,
    Panel: AiGenerator,
  },
  {
    value: "write",
    label: "Write your own",
    description: "Type a question, its four options and the answer.",
    icon: PencilSquareIcon,
    Panel: WriteQuestion,
  },
  {
    value: "import",
    label: "Import from a sheet",
    description: "Upload many at once from Excel or Google Sheets (CSV).",
    icon: TableCellsIcon,
    Panel: ImportQuestions,
  },
];

/**
 * Three ways to add multiple-choice questions to the bank. Every panel stays
 * mounted, so switching tabs never loses AI drafts or a half-written question.
 */
const AddQuestions = () => {
  const [params, setParams] = useSearchParams();
  const tab = METHODS.some((m) => m.value === params.get("tab")) ? params.get("tab") : "ai";

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Question bank"
        title="Add questions"
        description="Everything you add goes to your institution's question bank, ready to use in tests."
        actions={
          <Link to="/questions" className={buttonStyles({ variant: "secondary" })}>
            Open question bank
          </Link>
        }
      />

      <div role="tablist" aria-label="How to add questions" className="grid gap-3 sm:grid-cols-3">
        {METHODS.map((m) => {
          const active = m.value === tab;
          return (
            <button
              key={m.value}
              id={`tab-${m.value}`}
              type="button"
              role="tab"
              aria-selected={active}
              aria-controls={`panel-${m.value}`}
              onClick={() => setParams({ tab: m.value }, { replace: true })}
              className={cx(
                "flex items-start gap-3 rounded-lg border bg-white p-4 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500",
                active ? "border-accent-600 ring-1 ring-accent-600" : "border-slate-200 hover:border-slate-300"
              )}
            >
              <span
                className={cx(
                  "flex size-9 shrink-0 items-center justify-center rounded-lg ring-1",
                  active ? "bg-accent-600 text-white ring-accent-600" : "bg-slate-50 text-slate-500 ring-slate-200"
                )}
              >
                <m.icon className="size-5" />
              </span>
              <span>
                <span className={cx("block text-sm font-semibold", active ? "text-accent-800" : "text-slate-900")}>
                  {m.label}
                </span>
                <span className="mt-0.5 block text-[13px] text-slate-500">{m.description}</span>
              </span>
            </button>
          );
        })}
      </div>

      {METHODS.map((method) => (
        <div
          key={method.value}
          id={`panel-${method.value}`}
          role="tabpanel"
          aria-labelledby={`tab-${method.value}`}
          hidden={method.value !== tab}
        >
          <method.Panel />
        </div>
      ))}
    </div>
  );
};

export default AddQuestions;
