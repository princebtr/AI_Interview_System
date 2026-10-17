// One exam layout for every proctored sitting: scheduled tests, practice tests and
// AI interviews. Top bar (test, clock, check counts, exit) · question list ·
// question card · live proctoring panel.
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  BookmarkIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
} from "@heroicons/react/20/solid";
import {
  ArrowRightStartOnRectangleIcon,
  ArrowsPointingOutIcon,
  ComputerDesktopIcon,
  DevicePhoneMobileIcon,
  MicrophoneIcon,
  ShieldCheckIcon,
  UsersIcon,
  VideoCameraIcon,
  WindowIcon,
} from "@heroicons/react/24/outline";
import { useAuth } from "../context/AuthContext";
import { Badge, Button, Card, InstitutionLogo, LiveDot, Spinner } from "./ui";
import { StreamVideo } from "./proctoring";
import { cx } from "../utils/helpers";
import { countdown } from "../utils/time";

/* ---------------------------------------------------------------------------- */
/* Clock and check chips                                                         */
/* ---------------------------------------------------------------------------- */

const clockText = (ms) => {
  const total = Math.max(0, Math.floor(ms / 1000));
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`;
};

/** Time remaining (`remaining` ms, turns amber then red) or elapsed (`elapsed` ms). */
const ClockPill = ({ remaining, elapsed }) => {
  const counting = remaining != null;
  const ms = counting ? remaining : elapsed;
  const tone = !counting
    ? "bg-accent-50 text-accent-900 ring-accent-100"
    : ms < 60_000
      ? "bg-red-600 text-white ring-red-600"
      : ms < 5 * 60_000
        ? "bg-amber-50 text-amber-900 ring-amber-200"
        : "bg-accent-50 text-accent-900 ring-accent-100";
  const label = counting ? "Time remaining" : "Time elapsed";
  return (
    <div
      role="timer"
      aria-label={`${label} ${countdown(ms)}`}
      className={cx("flex items-center gap-2.5 rounded-lg px-3 py-1.5 ring-1", tone)}
    >
      <ClockIcon className="size-5 shrink-0 opacity-80" />
      <div className="leading-tight">
        <p className="font-mono text-[15px] font-bold tabular-nums">{clockText(ms)}</p>
        <p className="text-[10px] font-medium opacity-70">{label}</p>
      </div>
    </div>
  );
};

const CHIP = {
  screen_switch: {
    label: "Full screen",
    icon: ArrowsPointingOutIcon,
    tone: "bg-blue-50 text-blue-700 ring-blue-100",
  },
  voice: {
    label: "Microphone",
    icon: MicrophoneIcon,
    tone: "bg-emerald-50 text-emerald-700 ring-emerald-100",
  },
  face: {
    label: "Camera",
    icon: VideoCameraIcon,
    tone: "bg-orange-50 text-orange-700 ring-orange-100",
  },
  phone: {
    label: "Phone",
    icon: DevicePhoneMobileIcon,
    tone: "bg-rose-50 text-rose-700 ring-rose-100",
  },
  tabs: {
    label: "Tab switches",
    icon: WindowIcon,
    tone: "bg-violet-50 text-violet-700 ring-violet-100",
  },
};

const CheckChip = ({ chipKey, count, limit }) => {
  const meta = CHIP[chipKey];
  const Icon = meta.icon;
  const danger = limit > 0 && count >= limit - 1 && count > 0;
  return (
    <li
      title={`${meta.label}: ${count}${limit ? ` of ${limit}` : ""}`}
      className={cx(
        "flex min-w-16 flex-col items-center rounded-lg px-2.5 py-1 ring-1",
        danger ? "bg-red-50 text-red-700 ring-red-200" : meta.tone,
      )}
    >
      <span className="flex items-center gap-1 text-[13px] font-bold tabular-nums">
        {Icon && <Icon className="size-4" aria-hidden="true" />}
        {count}
        {limit > 0 && <span className="font-medium opacity-60">/{limit}</span>}
      </span>
      <span className="hidden text-[10px] font-medium opacity-80 sm:block">{meta.label}</span>
    </li>
  );
};

/* ---------------------------------------------------------------------------- */
/* Shell                                                                         */
/* ---------------------------------------------------------------------------- */

/**
 * Full-viewport exam layout, above the app's navigation.
 * - `title`, `icon`: what is being sat; `clock`: { remaining } or { elapsed } in ms
 * - `chips`: [{ key, count, limit }] (keys: screen_switch, voice, face, phone, tabs)
 * - `actions`: the exit/submit controls (top right)
 * - `sidebar` (question list), `panel` (proctoring), `children` (the question)
 * - `notices`: banners above the columns (device lost, time up)
 */
export const ExamShell = ({ title, icon: Icon, clock, chips = [], actions, notices, sidebar, panel, children }) => {
  const { user } = useAuth();
  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-slate-50">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-slate-200 bg-white px-4 py-2.5 shadow-soft sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <InstitutionLogo institution={user?.institution} className="size-9" />
          <span className="hidden truncate text-[15px] font-bold text-slate-900 md:block">
            {user?.institution?.name ?? "Cohortix"}
          </span>
          <span className="hidden h-6 w-px bg-slate-200 md:block" aria-hidden="true" />
          <span className="flex min-w-0 items-center gap-2">
            {Icon && (
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent-50 text-accent-600">
                <Icon className="size-[18px]" />
              </span>
            )}
            <span className="truncate text-sm font-semibold text-slate-900 sm:text-[15px]">{title}</span>
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {clock && <ClockPill {...clock} />}
          {chips.length > 0 && (
            <ul className="flex items-center gap-1.5" aria-label="Proctoring counts">
              {chips.map((c) => (
                <CheckChip key={c.key} chipKey={c.key} count={c.count} limit={c.limit} />
              ))}
            </ul>
          )}
          {actions}
        </div>
      </header>
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[1600px] space-y-4 p-4 sm:p-5">
          {notices}
          <div
            className={cx(
              "grid items-start gap-5",
              sidebar && panel
                ? "lg:grid-cols-[minmax(0,1fr)_300px] xl:grid-cols-[240px_minmax(0,1fr)_300px]"
                : panel
                  ? "lg:grid-cols-[minmax(0,1fr)_300px]"
                  : sidebar
                    ? "xl:grid-cols-[240px_minmax(0,1fr)]"
                    : "",
            )}
          >
            {sidebar && <aside className="hidden xl:sticky xl:top-0 xl:block">{sidebar}</aside>}
            <main className="min-w-0">{children}</main>
            {panel && <aside className="lg:sticky lg:top-0">{panel}</aside>}
          </div>
        </div>
      </div>
    </div>
  );
};

/** The red "Quit test" button of the top bar. */
export const QuitButton = ({ children = "Quit test", ...props }) => (
  <Button variant="quit" {...props}>
    {children}
    <ArrowRightStartOnRectangleIcon className="size-4" />
  </Button>
);

/* ---------------------------------------------------------------------------- */
/* Question list (left)                                                          */
/* ---------------------------------------------------------------------------- */

/** items: [{ key, label, done, flagged, badge }] */
export const QuestionList = ({ title = "Questions", items, current, onSelect }) => (
  <Card className="p-3">
    <div className="px-2 pt-1 pb-3">
      <p className="text-[15px] font-bold text-slate-900">{title}</p>
      <p className="text-[12px] text-slate-500">
        {items.length} question{items.length === 1 ? "" : "s"}
      </p>
    </div>
    <ol className="max-h-[calc(100vh-14rem)] space-y-1 overflow-y-auto">
      {items.map((item, i) => {
        const active = i === current;
        return (
          <li key={item.key}>
            <button
              type="button"
              onClick={onSelect ? () => onSelect(i) : undefined}
              disabled={!onSelect}
              aria-current={active ? "step" : undefined}
              className={cx(
                "flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-colors disabled:cursor-default",
                active ? "bg-accent-50" : onSelect && "hover:bg-slate-50",
              )}
            >
              <span
                className={cx(
                  "relative flex size-7 shrink-0 items-center justify-center rounded-full text-[12px] font-bold tabular-nums",
                  active ? "bg-primary text-on-primary" : "bg-slate-100 text-slate-600",
                )}
              >
                {i + 1}
                {item.flagged && (
                  <span className="absolute -top-0.5 -right-0.5 size-2.5 rounded-full bg-amber-500 ring-2 ring-white" />
                )}
              </span>
              <span
                className={cx(
                  "min-w-0 flex-1 truncate text-[13px]",
                  active ? "font-semibold text-accent-800" : "text-slate-700",
                )}
              >
                {item.label}
              </span>
              {item.badge ??
                (item.done && <CheckCircleIcon className="size-5 shrink-0 text-emerald-500" aria-label="Answered" />)}
            </button>
          </li>
        );
      })}
    </ol>
  </Card>
);

/* ---------------------------------------------------------------------------- */
/* Question card (centre)                                                        */
/* ---------------------------------------------------------------------------- */

const LETTERS = ["A", "B", "C", "D"];

/** Header with the subject, "Question X of N" and progress. */
export const QuestionHeader = ({ subject, icon: Icon, position, total, done }) => {
  const percent = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="border-b border-slate-100 px-5 py-4 sm:px-6">
      <div className="flex items-center justify-between gap-4">
        <span className="flex min-w-0 items-center gap-2.5">
          {Icon && (
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-50 text-accent-600">
              <Icon className="size-5" />
            </span>
          )}
          <span className="truncate text-lg font-bold text-slate-900">{subject}</span>
        </span>
        {total ? (
          <span className="shrink-0 text-[13px] text-slate-500 tabular-nums">
            Question {position + 1} of {total}
          </span>
        ) : (
          <span className="shrink-0 text-[13px] text-slate-500 tabular-nums">Question {position + 1}</span>
        )}
      </div>
      {total > 0 && (
        <div className="mt-3 flex items-center gap-3">
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
            <div
              className="bg-primary h-full rounded-full transition-[width] duration-300"
              style={{ width: `${percent}%` }}
            />
          </div>
          <span className="shrink-0 text-[12px] font-medium text-slate-500 tabular-nums">{percent}% complete</span>
        </div>
      )}
    </div>
  );
};

export const QuestionTags = ({ tags, action }) => (
  <div className="flex flex-wrap items-center justify-between gap-3">
    <div className="flex flex-wrap gap-2">
      {tags.filter(Boolean).map((tag, i) => (
        <span
          key={tag}
          className={cx(
            "rounded-full px-3 py-1 text-[12px] font-medium",
            i === 0 ? "bg-accent-50 text-accent-700" : "bg-slate-100 text-slate-600",
          )}
        >
          {tag}
        </span>
      ))}
    </div>
    {action}
  </div>
);

export const ReviewToggle = ({ flagged, onToggle, disabled }) => (
  <button
    type="button"
    onClick={onToggle}
    disabled={disabled}
    aria-pressed={flagged}
    className={cx(
      "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[13px] font-semibold transition-colors disabled:opacity-50",
      flagged
        ? "border-amber-300 bg-amber-50 text-amber-900"
        : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50",
    )}
  >
    <BookmarkIcon className={cx("size-4", flagged ? "text-amber-600" : "text-slate-400")} />
    {flagged ? "Marked for review" : "Mark for review"}
  </button>
);

/** Four options as radios: a radio circle, the letter and the text. */
export const OptionList = ({ labelledBy, options, selected, onSelect, disabled }) => (
  <div role="radiogroup" aria-labelledby={labelledBy} className="space-y-3">
    {LETTERS.filter((letter) => options[letter] != null).map((letter) => {
      const on = selected === letter;
      return (
        <button
          key={letter}
          type="button"
          role="radio"
          aria-checked={on}
          disabled={disabled}
          onClick={() => onSelect(letter)}
          className={cx(
            "flex w-full items-center gap-4 rounded-xl border px-4 py-3.5 text-left text-[15px] transition-all duration-150 disabled:cursor-not-allowed",
            on
              ? "border-accent-400 bg-accent-50/70 text-slate-900 shadow-soft"
              : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50",
          )}
        >
          <span
            className={cx(
              "flex size-5 shrink-0 items-center justify-center rounded-full border-2",
              on ? "border-accent-600" : "border-slate-300",
            )}
            aria-hidden="true"
          >
            {on && <span className="size-2.5 rounded-full bg-accent-600" />}
          </span>
          <span
            className={cx(
              "flex size-8 shrink-0 items-center justify-center rounded-full text-[13px] font-bold",
              on ? "bg-primary text-on-primary" : "bg-slate-100 text-slate-700",
            )}
          >
            {letter}
          </span>
          <span>{options[letter]}</span>
        </button>
      );
    })}
  </div>
);

/** Previous · numbered pager · next/submit. `done(i)` marks answered numbers. */
export const QuestionFooter = ({ position, total, onJump, done, nextAction, onPrevious }) => (
  <div className="flex flex-col gap-3 border-t border-slate-100 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
    <Button variant="secondary" size="lg" onClick={onPrevious} disabled={position === 0}>
      <ArrowLeftIcon className="size-4" />
      Previous
    </Button>
    {total > 1 && onJump && (
      <nav aria-label="Question numbers" className="flex flex-wrap justify-center gap-1.5">
        {Array.from({ length: total }, (_, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onJump(i)}
            aria-current={i === position ? "step" : undefined}
            aria-label={`Question ${i + 1}${done?.(i) ? ", answered" : ""}`}
            className={cx(
              "size-9 rounded-lg text-[13px] font-semibold tabular-nums transition-colors",
              i === position
                ? "bg-primary text-on-primary shadow-button"
                : done?.(i)
                  ? "bg-accent-100 text-accent-800 hover:bg-accent-200"
                  : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50",
            )}
          >
            {i + 1}
          </button>
        ))}
      </nav>
    )}
    {nextAction}
  </div>
);

export const NextButton = ({ children = "Next question", ...props }) => (
  <Button size="lg" {...props}>
    {children}
    <ArrowRightIcon className="size-4" />
  </Button>
);

/* ---------------------------------------------------------------------------- */
/* Proctoring panel (right)                                                      */
/* ---------------------------------------------------------------------------- */

const ROW_ICONS = {
  people: UsersIcon,
  phone: DevicePhoneMobileIcon,
  microphone: MicrophoneIcon,
  fullscreen: ComputerDesktopIcon,
  tabs: WindowIcon,
};

const ROW_STATE = {
  ok: {
    text: "text-emerald-700",
    icon: <CheckCircleIcon className="size-5 text-emerald-500" />,
  },
  notice: {
    text: "text-amber-700",
    icon: <ExclamationCircleIcon className="size-5 text-amber-500" />,
  },
  warn: {
    text: "text-orange-700",
    icon: <ExclamationTriangleIcon className="size-5 text-orange-500" />,
  },
  checking: {
    text: "text-slate-500",
    icon: <Spinner className="size-4 text-slate-400" />,
  },
};

/**
 * rows: [{ key, label, state: "ok" | "notice" | "warn" | "checking", text }]
 * boxes: where a phone may be in the latest check, [[x1, y1, x2, y2, confidence]] (0-1)
 */
export const ProctorSidebar = ({
  stream,
  rows,
  boxes = [],
  note = "Checks run every few seconds. Nothing is recorded.",
}) => (
  <Card className="p-4">
    <div className="flex items-start justify-between gap-3">
      <span className="flex items-start gap-2.5">
        <ShieldCheckIcon className="size-8 shrink-0 text-emerald-600" />
        <span>
          <span className="block text-[15px] font-bold text-slate-900">Proctoring</span>
          <span className="block text-[12px] leading-snug text-slate-500">
            Your test is being monitored in real time
          </span>
        </span>
      </span>
      <Badge tone="danger">
        <LiveDot />
        Live
      </Badge>
    </div>
    {stream?.getVideoTracks().length > 0 && (
      <div className="relative mt-4 aspect-[4/3] -scale-x-100 overflow-hidden rounded-xl bg-slate-900">
        <StreamVideo stream={stream} className="size-full object-cover" />
        {boxes.map(([x1, y1, x2, y2], i) => (
          <span
            key={i}
            aria-hidden="true"
            className="absolute rounded border-2 border-orange-400"
            style={{
              left: `${x1 * 100}%`,
              top: `${y1 * 100}%`,
              width: `${(x2 - x1) * 100}%`,
              height: `${(y2 - y1) * 100}%`,
            }}
          />
        ))}
      </div>
    )}
    <ul className="mt-4 space-y-2.5">
      {rows.map((row) => {
        const Icon = ROW_ICONS[row.key] ?? InformationCircleIcon;
        const state = ROW_STATE[row.state] ?? ROW_STATE.checking;
        return (
          <li
            key={row.key}
            className="flex items-center gap-3 rounded-xl border border-slate-200/80 bg-white px-3 py-2.5"
          >
            <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-600">
              {Icon && <Icon className="size-[18px]" />}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[12px] text-slate-500">{row.label}</span>
              <span className={cx("block truncate text-sm font-semibold", state.text)}>{row.text}</span>
            </span>
            {state.icon}
          </li>
        );
      })}
    </ul>
    <p className="mt-4 flex gap-2 rounded-xl bg-slate-50 px-3 py-2.5 text-[12px] leading-relaxed text-slate-600">
      <InformationCircleIcon className="mt-px size-4 shrink-0 text-accent-600" />
      {note}
    </p>
  </Card>
);
