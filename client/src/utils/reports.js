// Constants and formatters shared by the report charts and pages.

// Categorical slots 1-3 of the validated reference palette (light surface; the
// app has no dark theme). Validated all-pairs on #ffffff: worst CVD ΔE 9.2,
// normal-vision ΔE 24. Aqua is under 3:1 contrast against white, so every chart
// ships a legend and a table view.
export const SERIES = {
  practice: { label: "Practice tests", color: "#2a78d6" },
  interview: { label: "AI interview", color: "#eb6834" },
  tests: { label: "Scheduled tests", color: "#1baf7a" },
};
export const SINGLE = "#2a78d6"; // single-series magnitude (sessions, students, averages)

export const RANGES = [
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 180, label: "6 months" },
  { days: 365, label: "12 months" },
];

const dayMonth = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" });
const fullDate = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" });
// Week keys are ISO dates (the Monday); parse as a local date, not UTC midnight.
const weekDate = (iso) => {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
};
export const weekLabel = (iso) => dayMonth.format(weekDate(iso));
export const weekTitle = (iso) => `Week of ${fullDate.format(weekDate(iso))}`;
export const dateLabel = (value) => (value ? fullDate.format(new Date(value)) : "—");
