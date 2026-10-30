// Building blocks shared by the student report and the staff overview.
import { ChartCard, ColumnChart, DataTable, HBarChart, LineChart, Legend } from "./charts";
import { cx } from "../utils/helpers";
import { formatPercent } from "../utils/scores";
import { RANGES, SERIES, weekLabel, weekTitle } from "../utils/reports";

/** Date range presets as a segmented control (the first filter in the row). */
export const RangeFilter = ({ value, onChange }) => (
  <div role="radiogroup" aria-label="Date range" className="flex rounded-md bg-slate-100 p-0.5 text-[13px]">
    {RANGES.map((r) => (
      <button
        key={r.days}
        type="button"
        role="radio"
        aria-checked={value === r.days}
        onClick={() => onChange(r.days)}
        className={cx(
          "h-8 rounded px-3 font-medium whitespace-nowrap transition-colors",
          value === r.days ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-800"
        )}
      >
        {r.label}
      </button>
    ))}
  </div>
);

const TREND_SERIES = ["practice", "interview", "tests"].map((key) => ({ key, ...SERIES[key] }));

/** Weekly average scores: practice tests, AI interview answers and scheduled tests (one 0-100% axis). */
export const ScoreTrendCard = ({ trend, busy, description = "Weekly average score" }) => {
  const any = trend.some((w) => TREND_SERIES.some((s) => w[s.key] !== null));
  return (
    <ChartCard
      title="Scores over time"
      description={description}
      busy={busy}
      legend={any && <Legend items={TREND_SERIES} />}
      table={
        <DataTable
          caption="Weekly average scores"
          columns={[
            { key: "week", label: "Week", format: weekTitle },
            ...TREND_SERIES.map((s) => ({ key: s.key, label: s.label, align: "right", format: formatPercent })),
          ]}
          rows={trend}
        />
      }
    >
      {any ? (
        <LineChart
          data={trend}
          xKey="week"
          xFormat={weekLabel}
          tooltipTitle={weekTitle}
          series={TREND_SERIES}
          yFormat={(v) => `${Math.round(v)}%`}
        />
      ) : (
        <p className="py-16 text-center text-[13px] text-slate-500">No scores in this period.</p>
      )}
    </ChartCard>
  );
};

/** One count per week, e.g. practice sessions or active students. */
export const WeeklyCountCard = ({ title, description, trend, yKey, yLabel, busy }) => (
  <ChartCard
    title={title}
    description={description}
    busy={busy}
    table={
      <DataTable
        caption={title}
        columns={[
          { key: "week", label: "Week", format: weekTitle },
          { key: yKey, label: yLabel, align: "right" },
        ]}
        rows={trend}
      />
    }
  >
    <ColumnChart data={trend} xKey="week" xFormat={weekLabel} tooltipTitle={weekTitle} yKey={yKey} yLabel={yLabel} />
  </ChartCard>
);

/** Average practice score per subject. */
export const SubjectsCard = ({ subjects, busy }) => (
  <ChartCard
    title="By subject"
    description="Average practice score, most practised first"
    busy={busy}
    table={
      <DataTable
        caption="Average practice score by subject"
        columns={[
          { key: "subject", label: "Subject" },
          { key: "attempts", label: "Sessions", align: "right" },
          { key: "averageScore", label: "Average", align: "right", format: formatPercent },
        ]}
        rows={subjects}
      />
    }
  >
    <HBarChart
      items={subjects.map((s) => ({
        key: s.subject,
        label: s.subject,
        sub: `${s.attempts} session${s.attempts === 1 ? "" : "s"}`,
        value: s.averageScore,
      }))}
      format={formatPercent}
      empty="No practice in this period."
    />
  </ChartCard>
);
