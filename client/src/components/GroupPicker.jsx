import { Select } from "./ui";
import { cx } from "../utils/helpers";
import { EMPTY_SELECTION, LEVELS, LEVEL_META, optionsFor } from "../utils/structure";

/**
 * Cascading Batch -> Department -> Section -> Cohort selects over the tree from
 * GET /institution/structure. `value` is a selection ({batch, department,
 * section, cohort} ids, "" when not chosen); changing a level clears the ones below.
 *
 * - mode="filter": every level is optional ("All batches", ...), compact, no labels.
 * - mode="form": labelled; stop at any level unless `requireCohort`.
 */
const GroupPicker = ({
  tree,
  value,
  onChange,
  mode = "form",
  requireCohort = false,
  error,
  idPrefix = "group",
  className,
  showCounts = false,
}) => {
  const filter = mode === "filter";
  const options = optionsFor(tree, value);
  // The error shows on the first level still to choose.
  const errorLevel = error ? (LEVELS.find((l) => !value[l]) ?? LEVELS[LEVELS.length - 1]) : null;

  const choose = (level, id) => {
    const next = { ...EMPTY_SELECTION };
    for (const l of LEVELS) {
      if (l === level) {
        next[l] = id;
        break;
      }
      next[l] = value[l];
    }
    onChange(next);
  };

  return (
    <div className={cx("grid gap-2", filter ? "grid-cols-2 lg:grid-cols-4" : "gap-3 sm:grid-cols-2", className)}>
      {LEVELS.map((level, i) => {
        const meta = LEVEL_META[level];
        const parentChosen = i === 0 || Boolean(value[LEVELS[i - 1]]);
        const nodes = options[level];
        const placeholder = filter
          ? `All ${meta.plural.toLowerCase()}`
          : !parentChosen
            ? `Choose a ${LEVEL_META[LEVELS[i - 1]].label.toLowerCase()} first`
            : nodes.length === 0
              ? `No ${meta.plural.toLowerCase()} yet`
              : requireCohort || i === 0
                ? `Choose a ${meta.label.toLowerCase()}`
                : `All ${meta.plural.toLowerCase()}`;
        return (
          <Select
            key={level}
            id={`${idPrefix}-${level}`}
            label={filter ? undefined : meta.label}
            aria-label={filter ? `Filter by ${meta.label.toLowerCase()}` : undefined}
            compact={filter}
            disabled={!parentChosen || nodes.length === 0}
            value={value[level]}
            error={level === errorLevel ? error : undefined}
            onChange={(e) => choose(level, e.target.value)}
          >
            <option value="">{placeholder}</option>
            {nodes.map((node) => (
              <option key={node.id} value={node.id}>
                {node.name}
                {showCounts ? ` (${node.studentCount})` : ""}
              </option>
            ))}
          </Select>
        );
      })}
    </div>
  );
};

export default GroupPicker;
