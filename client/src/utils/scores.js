export const formatPercent = (value) =>
  value === null || value === undefined ? "—" : `${Math.round(value)}%`;

/** Background class for a 0–100 score: green ≥ 80, amber ≥ 60, red below, grey when missing. */
export const scoreTone = (value) =>
  value === null || value === undefined
    ? "bg-slate-200"
    : value >= 80
      ? "bg-emerald-500"
      : value >= 60
        ? "bg-amber-500"
        : "bg-red-500";
