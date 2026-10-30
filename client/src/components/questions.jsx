// Shared pieces for multiple-choice questions (question bank, adding questions).
import { CheckIcon } from "@heroicons/react/20/solid";
import { SparklesIcon } from "@heroicons/react/24/outline";
import { Badge } from "./ui";
import { cx } from "../utils/helpers";
import { LETTERS } from "../utils/questions";

const DIFFICULTY_TONE = { easy: "success", medium: "info", hard: "warning" };

export const DifficultyBadge = ({ value }) =>
  value ? (
    <Badge tone={DIFFICULTY_TONE[value] ?? "neutral"} className="capitalize">
      {value}
    </Badge>
  ) : null;

export const AiBadge = () => (
  <Badge tone="ai">
    <SparklesIcon className="size-3" />
    AI
  </Badge>
);

/** The four options with the correct one marked. */
export const OptionList = ({ options, correct, compact = false }) => (
  <ul className={cx("grid gap-1.5", !compact && "sm:grid-cols-2")}>
    {LETTERS.map((letter) => {
      const isCorrect = letter === correct;
      return (
        <li
          key={letter}
          className={cx(
            "flex items-start gap-2.5 rounded-md border px-3 py-2 text-[13px]",
            isCorrect ? "border-emerald-300 bg-emerald-50/70 text-slate-900" : "border-slate-200 text-slate-700"
          )}
        >
          <span
            className={cx(
              "flex size-5 shrink-0 items-center justify-center rounded font-mono text-[11px] font-medium",
              isCorrect ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-500"
            )}
          >
            {isCorrect ? <CheckIcon className="size-3.5" aria-label="Correct answer" /> : letter}
          </span>
          <span className="pt-px">{options?.[letter]}</span>
        </li>
      );
    })}
  </ul>
);

/** A small segmented control, e.g. difficulty or question count. */
export const Segmented = ({ label, options, value, onChange }) => (
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
