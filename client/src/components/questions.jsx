// Shared display pieces for multiple-choice questions (question bank, AI generator).
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
