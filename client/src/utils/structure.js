// The academic structure: Batch -> Department -> Section -> Cohort.
// The server sends it as a tree (GET /institution/structure): each batch has
// `children` (departments), and so on down to cohorts.

export const LEVELS = ["batch", "department", "section", "cohort"];

export const LEVEL_META = {
  batch: { label: "Batch", plural: "Batches", example: "e.g. 2023-2027" },
  department: { label: "Department", plural: "Departments", example: "e.g. Computer Science" },
  section: { label: "Section", plural: "Sections", example: "e.g. A" },
  cohort: { label: "Cohort", plural: "Cohorts", example: "e.g. Lab group 1" },
};

export const childLevel = (level) => LEVELS[LEVELS.indexOf(level) + 1] ?? null;

/** A selection names one node per level; "" means "not chosen". */
export const EMPTY_SELECTION = { batch: "", department: "", section: "", cohort: "" };

/** The nodes to offer at each level for a selection: {batch: [...], department: [...], ...}. */
export const optionsFor = (tree, selection) => {
  const options = {};
  let nodes = tree ?? [];
  for (const level of LEVELS) {
    options[level] = nodes;
    nodes = nodes.find((n) => n.id === selection[level])?.children ?? [];
  }
  return options;
};

/** Drop choices that no longer exist or don't sit under the level above. */
export const validSelection = (tree, selection) => {
  const result = { ...EMPTY_SELECTION };
  let nodes = tree ?? [];
  for (const level of LEVELS) {
    const node = nodes.find((n) => n.id === selection?.[level]);
    if (!node) break;
    result[level] = node.id;
    nodes = node.children ?? [];
  }
  return result;
};

/** The deepest chosen level as {level, id}, or null when nothing is chosen. */
export const deepest = (selection) => {
  for (const level of [...LEVELS].reverse()) {
    if (selection?.[level]) return { level, id: selection[level] };
  }
  return null;
};

/** Query params for a list filtered by a selection: the deepest choice implies the rest. */
export const selectionParams = (selection) => {
  const target = deepest(selection);
  return target ? { [target.level]: target.id } : {};
};

/** A selection from a node's `path` ([{level, id, name}, ...]). */
export const selectionFromPath = (path) => ({
  ...EMPTY_SELECTION,
  ...Object.fromEntries((path ?? []).map((p) => [p.level, p.id])),
});

/** A selection from a user's `placement` ({batch: {id, name}, ...}). */
export const selectionFromPlacement = (placement) =>
  Object.fromEntries(LEVELS.map((level) => [level, placement?.[level]?.id ?? ""]));

/** The node for a selection's deepest choice, or null. */
export const selectedNode = (tree, selection) => {
  let nodes = tree ?? [];
  let found = null;
  for (const level of LEVELS) {
    if (!selection?.[level]) break;
    found = nodes.find((n) => n.id === selection[level]) ?? null;
    if (!found) return null;
    nodes = found.children ?? [];
  }
  return found;
};

/** Every node in the tree, depth first. */
export const flatten = (tree) => (tree ?? []).flatMap((node) => [node, ...flatten(node.children)]);
