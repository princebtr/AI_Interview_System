// Charts for reports: plain SVG, no chart library.
//
// Specs (see the data-viz guidelines): 2px lines, >= 8px markers with a 2px
// surface ring, bars <= 24px with 4px rounded ends square at the baseline,
// hairline recessive grid, one y-axis, a legend for 2+ series, text in text
// colours (never the series colour), a hover/focus tooltip that enhances but
// never gates, and a table view for every chart.
import { useEffect, useRef, useState } from "react";
import { Card } from "./ui";
import { cx } from "../utils/helpers";
import { SINGLE } from "../utils/reports";

const GRID = "#e8e7e2";
const BASELINE = "#c3c2b7";
const SURFACE = "#ffffff";

const useWidth = () => {
  const ref = useRef(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!ref.current) return undefined;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
};

/** A clean axis maximum (and 4 ticks) above `value`. */
const niceMax = (value) => {
  if (!value || value <= 4) return 4;
  const step = 10 ** Math.floor(Math.log10(value / 4));
  const nice = [1, 2, 2.5, 5, 10].map((m) => m * step).find((s) => s * 4 >= value);
  return nice * 4;
};

const compact = (n) => (n >= 1000 ? `${Math.round(n / 100) / 10}K` : `${n}`);

/** A card with a title, legend, and a Chart / Table switch (the table is the chart's accessible twin). */
export const ChartCard = ({ title, description, legend, table, children, className, busy }) => {
  const [view, setView] = useState("chart");
  return (
    <Card className={cx("flex flex-col", className)}>
      <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          {description && <p className="mt-0.5 text-[12px] text-slate-500">{description}</p>}
        </div>
        {table && (
          <div role="group" aria-label={`${title}: view`} className="flex rounded-md bg-slate-100 p-0.5 text-[12px]">
            {["chart", "table"].map((v) => (
              <button
                key={v}
                type="button"
                aria-pressed={view === v}
                onClick={() => setView(v)}
                className={cx(
                  "rounded px-2 py-0.5 font-medium capitalize transition-colors",
                  view === v ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-800"
                )}
              >
                {v}
              </button>
            ))}
          </div>
        )}
      </div>
      {legend && view === "chart" && <div className="px-5 pt-2">{legend}</div>}
      <div className={cx("flex-1 px-5 pt-3 pb-4 transition-opacity", busy && "opacity-60")}>
        {view === "table" ? table : children}
      </div>
    </Card>
  );
};

/** Legend keys mirror the mark: a short line for lines, a square for bars, a tick for a marker. */
export const Legend = ({ items, mark = "line" }) => (
  <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-slate-600">
    {items.map((item) => (
      <li key={item.label} className="flex items-center gap-1.5">
        {(item.mark ?? mark) === "line" ? (
          <span className="h-0.5 w-3.5 rounded-full" style={{ background: item.color }} />
        ) : (item.mark ?? mark) === "tick" ? (
          <span className="h-3 w-0.5 rounded-full bg-slate-700" />
        ) : (
          <span className="size-2.5 rounded-[2px]" style={{ background: item.color }} />
        )}
        {item.label}
      </li>
    ))}
  </ul>
);

/** A small table for a chart's table view. `columns`: [{key, label, format?, align?}]. */
export const DataTable = ({ columns, rows, caption }) => (
  <div className="max-h-72 overflow-auto">
    <table className="w-full text-[13px]">
      {caption && <caption className="sr-only">{caption}</caption>}
      <thead className="sticky top-0 bg-white">
        <tr className="border-b border-slate-100 text-left text-[12px] text-slate-500">
          {columns.map((c) => (
            <th key={c.key} className={cx("px-2 py-1.5 font-medium", c.align === "right" && "text-right")}>
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {rows.map((row, i) => (
          <tr key={row.id ?? i}>
            {columns.map((c) => (
              <td
                key={c.key}
                className={cx("px-2 py-1.5 text-slate-700", c.align === "right" && "text-right tabular-nums")}
              >
                {c.format ? c.format(row[c.key], row) : (row[c.key] ?? "—")}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const Tooltip = ({ x, width, children }) => (
  <div
    role="status"
    className="pointer-events-none absolute top-0 z-10 min-w-36 rounded-md bg-white px-3 py-2 text-[12px] shadow-lg ring-1 ring-slate-900/10"
    style={x > width / 2 ? { right: width - x + 12 } : { left: x + 12 }}
  >
    {children}
  </div>
);

const PAD = { top: 8, right: 12, bottom: 24, left: 42 };
// A label at the right edge would be clipped if centred on its point.
const anchorAt = (x, width) => (x > width - 28 ? "end" : "middle");

/** Which x positions get a label: at most ~6, always the last. */
const labelIndexes = (count, width) => {
  const max = Math.max(2, Math.min(6, Math.floor(width / 72)));
  const step = Math.max(1, Math.ceil(count / max));
  const picked = new Set();
  for (let i = count - 1; i >= 0; i -= step) picked.add(i);
  return picked;
};

/**
 * Lines over evenly spaced x points (e.g. weeks). `series`: [{key, label, color}];
 * null values leave the point out and the line joins its neighbours. One y-axis.
 */
export const LineChart = ({ data, xKey, xFormat, tooltipTitle, series, yMax = 100, yFormat, height = 220 }) => {
  const [ref, width] = useWidth();
  const [active, setActive] = useState(null);
  const plotW = Math.max(0, width - PAD.left - PAD.right);
  const plotH = height - PAD.top - PAD.bottom;
  const n = data.length;
  const x = (i) => PAD.left + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const y = (v) => PAD.top + plotH - (v / yMax) * plotH;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * yMax);
  const labels = labelIndexes(n, plotW);

  const pick = (clientX) => {
    const rect = ref.current.getBoundingClientRect();
    const rel = clientX - rect.left - PAD.left;
    setActive(Math.max(0, Math.min(n - 1, Math.round(n <= 1 ? 0 : (rel / plotW) * (n - 1)))));
  };

  const onKey = (e) => {
    if (e.key === "ArrowRight") setActive((a) => Math.min(n - 1, (a ?? -1) + 1));
    else if (e.key === "ArrowLeft") setActive((a) => Math.max(0, (a ?? n) - 1));
    else if (e.key === "Escape") setActive(null);
    else return;
    e.preventDefault();
  };

  return (
    <div ref={ref} className="relative" style={{ height }}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={`${series.map((s) => s.label).join(", ")} over time`}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke={t === 0 ? BASELINE : GRID} />
              <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-slate-500 text-[11px] tabular-nums">
                {yFormat ? yFormat(t) : t}
              </text>
            </g>
          ))}
          {data.map((d, i) =>
            labels.has(i) ? (
              <text key={i} x={x(i)} y={height - 6} textAnchor={anchorAt(x(i), width)} className="fill-slate-500 text-[11px]">
                {xFormat(d[xKey])}
              </text>
            ) : null
          )}
          {active !== null && (
            <line x1={x(active)} x2={x(active)} y1={PAD.top} y2={PAD.top + plotH} stroke={BASELINE} />
          )}
          {series.map((s) => {
            const points = data.map((d, i) => [i, d[s.key]]).filter(([, v]) => v !== null && v !== undefined);
            const path = points.map(([i, v], k) => `${k ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
            return (
              <g key={s.key}>
                {points.length > 1 && (
                  <path d={path} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
                )}
                {points.map(([i, v]) => (
                  <circle
                    key={i}
                    cx={x(i)}
                    cy={y(v)}
                    r={active === i ? 5 : 4}
                    fill={s.color}
                    stroke={SURFACE}
                    strokeWidth={2}
                  />
                ))}
              </g>
            );
          })}
          {/* The crosshair layer: the whole plot is the hit target; arrow keys move it too. */}
          <rect
            x={PAD.left}
            y={PAD.top}
            width={plotW}
            height={plotH}
            fill="transparent"
            tabIndex={0}
            aria-label="Chart: use the arrow keys to read each week"
            className="cursor-crosshair outline-none focus-visible:stroke-accent-500"
            onPointerMove={(e) => pick(e.clientX)}
            onPointerLeave={() => setActive(null)}
            onBlur={() => setActive(null)}
            onKeyDown={onKey}
          />
        </svg>
      )}
      {active !== null && data[active] && (
        <Tooltip x={x(active)} width={width}>
          <p className="mb-1 text-slate-500">{(tooltipTitle ?? xFormat)(data[active][xKey])}</p>
          <ul className="space-y-0.5">
            {series.map((s) => (
              <li key={s.key} className="flex items-center gap-2">
                <span className="h-0.5 w-3 rounded-full" style={{ background: s.color }} />
                <span className="font-semibold text-slate-900 tabular-nums">
                  {data[active][s.key] === null || data[active][s.key] === undefined
                    ? "—"
                    : yFormat
                      ? yFormat(data[active][s.key])
                      : data[active][s.key]}
                </span>
                <span className="text-slate-500">{s.label}</span>
              </li>
            ))}
          </ul>
        </Tooltip>
      )}
    </div>
  );
};

const columnPath = (x, y, w, h) => {
  const r = Math.min(4, h, w / 2);
  return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`;
};

/** Single-series columns (e.g. sessions per week). Each column's band is its hover target. */
export const ColumnChart = ({ data, xKey, xFormat, tooltipTitle, yKey, yLabel, color = SINGLE, height = 200 }) => {
  const [ref, width] = useWidth();
  const [active, setActive] = useState(null);
  const plotW = Math.max(0, width - PAD.left - PAD.right);
  const plotH = height - PAD.top - PAD.bottom;
  const n = data.length;
  const band = n ? plotW / n : 0;
  const barW = Math.max(2, Math.min(24, band - 2)); // 2px surface gap between touching bars
  const yMax = niceMax(Math.max(0, ...data.map((d) => d[yKey] ?? 0)));
  const y = (v) => PAD.top + plotH - (v / yMax) * plotH;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * yMax);
  const labels = labelIndexes(n, plotW);

  return (
    <div ref={ref} className="relative" style={{ height }}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={yLabel}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke={t === 0 ? BASELINE : GRID} />
              <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-slate-500 text-[11px] tabular-nums">
                {compact(t)}
              </text>
            </g>
          ))}
          {data.map((d, i) => {
            const v = d[yKey] ?? 0;
            const cx0 = PAD.left + band * i + band / 2;
            const h = (v / yMax) * plotH;
            return (
              <g key={i}>
                {v > 0 && (
                  <path
                    d={columnPath(cx0 - barW / 2, PAD.top + plotH - h, barW, h)}
                    fill={color}
                    opacity={active === null || active === i ? 1 : 0.55}
                  />
                )}
                {labels.has(i) && (
                  <text x={cx0} y={height - 6} textAnchor={anchorAt(cx0, width)} className="fill-slate-500 text-[11px]">
                    {xFormat(d[xKey])}
                  </text>
                )}
                <rect
                  x={PAD.left + band * i}
                  y={PAD.top}
                  width={band}
                  height={plotH}
                  fill="transparent"
                  tabIndex={0}
                  aria-label={`${(tooltipTitle ?? xFormat)(d[xKey])}: ${v} ${yLabel}`}
                  className="outline-none"
                  onPointerEnter={() => setActive(i)}
                  onPointerLeave={() => setActive(null)}
                  onFocus={() => setActive(i)}
                  onBlur={() => setActive(null)}
                />
              </g>
            );
          })}
        </svg>
      )}
      {active !== null && data[active] && (
        <Tooltip x={PAD.left + band * active + band / 2} width={width}>
          <p className="text-slate-500">{(tooltipTitle ?? xFormat)(data[active][xKey])}</p>
          <p>
            <span className="font-semibold text-slate-900 tabular-nums">{data[active][yKey] ?? 0}</span>{" "}
            <span className="text-slate-500">{yLabel}</span>
          </p>
        </Tooltip>
      )}
    </div>
  );
};

/**
 * Horizontal bars on a 0-`max` scale with the value at the tip, e.g. average
 * score per subject. Optional `marker` per item draws a thin comparison tick
 * (e.g. the group's average). Items: [{key, label, sub?, value, marker?, href?, onClick?}].
 */
export const HBarChart = ({ items, max = 100, format, color = SINGLE, markerLabel, empty = "No data yet" }) => {
  if (!items.length) return <p className="py-8 text-center text-[13px] text-slate-500">{empty}</p>;
  return (
    <ul className="space-y-2.5">
      {items.map((item) => {
        const pct = (v) => `${Math.max(0, Math.min(100, ((v ?? 0) / max) * 100))}%`;
        const Label = item.onClick ? "button" : "span";
        return (
          <li key={item.key ?? item.label} className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)_3.25rem] items-center gap-3 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)_3.25rem]">
            <Label
              {...(item.onClick && { type: "button", onClick: item.onClick })}
              className={cx("min-w-0 text-left", item.onClick && "group")}
              title={item.label}
            >
              <span className={cx("block truncate text-[13px] text-slate-800", item.onClick && "group-hover:text-accent-700 group-hover:underline")}>
                {item.label}
              </span>
              {item.sub && <span className="block truncate text-[11px] text-slate-500">{item.sub}</span>}
            </Label>
            <div className="relative h-6" title={`${item.label}: ${item.value === null ? "no data" : format(item.value)}`}>
              <div className="absolute inset-y-0 left-0 w-full border-l" style={{ borderColor: BASELINE }} />
              {item.value !== null && item.value !== undefined && (
                <div
                  className="absolute top-1/2 left-0 h-3.5 -translate-y-1/2 rounded-r"
                  style={{ width: pct(item.value), background: color }}
                />
              )}
              {item.marker !== null && item.marker !== undefined && (
                <div
                  className="absolute inset-y-0.5 w-0.5 -translate-x-1/2 rounded-full bg-slate-700 ring-2 ring-white"
                  style={{ left: pct(item.marker) }}
                  aria-label={`${markerLabel}: ${format(item.marker)}`}
                />
              )}
            </div>
            <span className="text-right text-[13px] font-medium text-slate-900 tabular-nums">
              {item.value === null || item.value === undefined ? (item.emptyValue ?? "—") : format(item.value)}
            </span>
          </li>
        );
      })}
    </ul>
  );
};
