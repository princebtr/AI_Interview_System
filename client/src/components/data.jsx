// Presentational building blocks for dashboards: stat cards, bars, charts, empty states.
import { Link } from "react-router-dom";
import { ChevronRightIcon } from "@heroicons/react/20/solid";
import { Card } from "./ui";
import { cx } from "../utils/helpers";
import { formatPercent, scoreTone } from "../utils/scores";
import { shortDate } from "../utils/time";

export const StatGrid = ({ children, className }) => (
  <div className={cx("grid grid-cols-2 gap-4 lg:grid-cols-4", className)}>{children}</div>
);

export const StatCard = ({ label, value, sub, icon: Icon, to }) => {
  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <p className="text-[13px] font-medium text-slate-500">{label}</p>
        {Icon && (
          <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent-50 text-accent-700 ring-1 ring-accent-100">
            <Icon className="size-5" />
          </span>
        )}
      </div>
      <p className="mt-1 text-[1.75rem] leading-tight font-bold tracking-[-0.02em] text-slate-900 tabular-nums">{value}</p>
      {sub && <p className="mt-1 truncate text-[12px] text-slate-500">{sub}</p>}
    </>
  );
  return to ? (
    <Link
      to={to}
      className="block rounded-lg border border-slate-200/70 bg-white p-4 shadow-soft transition-all duration-200 ease-out hover:shadow-lift focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500 motion-safe:hover:-translate-y-1 sm:p-5"
    >
      {body}
    </Link>
  ) : (
    <Card className="p-4 sm:p-5">{body}</Card>
  );
};

export const ScoreBar = ({ value, className }) => (
  <div className={cx("h-1.5 overflow-hidden rounded-full bg-slate-100", className)}>
    <div
      className={cx("h-full rounded-full transition-[width] duration-500", scoreTone(value))}
      style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%` }}
    />
  </div>
);

/** Labelled horizontal bars, e.g. average score per subject. */
export const BarList = ({ items, valueLabel = formatPercent, emptyText = "No data yet" }) => {
  if (!items.length) return <p className="py-6 text-center text-[13px] text-slate-500">{emptyText}</p>;
  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item.key ?? item.label}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
            <span className="truncate text-slate-800">{item.label}</span>
            <span className="shrink-0 text-slate-500 tabular-nums">
              {item.meta && <span className="mr-2 text-[12px] text-slate-400">{item.meta}</span>}
              <span className="font-medium text-slate-900">{valueLabel(item.value)}</span>
            </span>
          </div>
          <ScoreBar value={item.value} />
        </li>
      ))}
    </ul>
  );
};

/** Bars for a daily series ({date, count}[]), oldest first. */
export const DailyBars = ({ data, label, unit = "sessions" }) => {
  const max = Math.max(1, ...data.map((d) => d.count));
  const total = data.reduce((n, d) => n + d.count, 0);
  return (
    <figure>
      <div className="flex h-36 items-end gap-1 sm:gap-1.5" role="img" aria-label={`${label}: ${total} ${unit} in ${data.length} days`}>
        {data.map((d) => (
          <div key={d.date} className="flex h-full flex-1 items-end" title={`${shortDate(d.date)} · ${d.count} ${unit}`}>
            <div
              className={cx("w-full rounded-sm transition-[height] duration-500", d.count ? "bg-primary" : "bg-slate-100")}
              style={{ height: d.count ? `${Math.max(6, (d.count / max) * 100)}%` : "4px" }}
            />
          </div>
        ))}
      </div>
      {data.length > 0 && (
        <figcaption className="mt-2 flex justify-between text-[11px] text-slate-400">
          <span>{shortDate(data[0].date)}</span>
          <span>Today</span>
        </figcaption>
      )}
    </figure>
  );
};

export const EmptyState = ({ icon: Icon, title, description, action, className }) => (
  <div className={cx("flex flex-col items-center px-6 py-10 text-center", className)}>
    {Icon && (
      <span className="flex size-12 items-center justify-center rounded-lg bg-accent-50 text-accent-600 ring-1 ring-accent-100">
        <Icon className="size-6" />
      </span>
    )}
    <p className="mt-4 text-sm font-semibold text-slate-900">{title}</p>
    {description && <p className="mt-1 max-w-sm text-[13px] leading-relaxed text-slate-500">{description}</p>}
    {action && <div className="mt-4 flex flex-wrap justify-center gap-2">{action}</div>}
  </div>
);

export const CardLink = ({ to, children }) => (
  <Link
    to={to}
    className="group inline-flex shrink-0 items-center gap-0.5 text-[13px] font-semibold whitespace-nowrap text-accent-700 hover:text-accent-800"
  >
    {children}
    <ChevronRightIcon className="size-4 transition-transform duration-200 motion-safe:group-hover:translate-x-0.5" />
  </Link>
);

export const LoadingBlock = ({ className = "h-40" }) => (
  <div className={cx("animate-pulse rounded-md bg-slate-100", className)} aria-label="Loading" />
);

export const LoadError = ({ onRetry }) => (
  <Card className="p-6 text-center">
    <p className="text-sm font-medium text-slate-900">Couldn't load this page</p>
    <p className="mt-1 text-[13px] text-slate-500">Check your connection and try again.</p>
    {onRetry && (
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 text-[13px] font-medium text-accent-700 hover:text-accent-800"
      >
        Retry
      </button>
    )}
  </Card>
);
