// Run with `npm test` (node --test).
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  EMPTY_SELECTION,
  deepest,
  flatten,
  optionsFor,
  selectedNode,
  selectionFromPath,
  selectionFromPlacement,
  selectionParams,
  validSelection,
} from "./structure.js";

const node = (level, id, children) => ({ level, id, name: id.toUpperCase(), ...(children && { children }) });
const TREE = [
  node("batch", "b1", [
    node("department", "d1", [node("section", "s1", [node("cohort", "c1"), node("cohort", "c2")])]),
    node("department", "d2", []),
  ]),
  node("batch", "b2", []),
];

describe("optionsFor", () => {
  it("offers only the children of each chosen level", () => {
    const options = optionsFor(TREE, { ...EMPTY_SELECTION, batch: "b1", department: "d1" });
    assert.deepEqual(options.batch.map((n) => n.id), ["b1", "b2"]);
    assert.deepEqual(options.department.map((n) => n.id), ["d1", "d2"]);
    assert.deepEqual(options.section.map((n) => n.id), ["s1"]);
    assert.deepEqual(options.cohort, []); // no section chosen yet
  });

  it("copes with no tree", () => {
    assert.deepEqual(optionsFor(undefined, EMPTY_SELECTION).batch, []);
  });
});

describe("deepest and selectionParams", () => {
  it("target the lowest chosen level", () => {
    const selection = { ...EMPTY_SELECTION, batch: "b1", department: "d1" };
    assert.deepEqual(deepest(selection), { level: "department", id: "d1" });
    assert.deepEqual(selectionParams(selection), { department: "d1" });
  });

  it("are empty when nothing is chosen", () => {
    assert.equal(deepest(EMPTY_SELECTION), null);
    assert.deepEqual(selectionParams(EMPTY_SELECTION), {});
  });
});

describe("validSelection", () => {
  it("keeps a consistent path", () => {
    const selection = { batch: "b1", department: "d1", section: "s1", cohort: "c2" };
    assert.deepEqual(validSelection(TREE, selection), selection);
  });

  it("drops choices that aren't under the level above, and everything below them", () => {
    const selection = { batch: "b2", department: "d1", section: "s1", cohort: "c1" };
    assert.deepEqual(validSelection(TREE, selection), { ...EMPTY_SELECTION, batch: "b2" });
  });
});

describe("selectedNode", () => {
  it("finds the node for the deepest choice", () => {
    assert.equal(selectedNode(TREE, { ...EMPTY_SELECTION, batch: "b1", department: "d1", section: "s1" }).id, "s1");
  });

  it("is null for nothing chosen or a broken path", () => {
    assert.equal(selectedNode(TREE, EMPTY_SELECTION), null);
    assert.equal(selectedNode(TREE, { ...EMPTY_SELECTION, batch: "b2", department: "d1" }), null);
  });
});

describe("selection builders", () => {
  it("read a node path", () => {
    const path = [
      { level: "batch", id: "b1" },
      { level: "department", id: "d1" },
    ];
    assert.deepEqual(selectionFromPath(path), { ...EMPTY_SELECTION, batch: "b1", department: "d1" });
  });

  it("read a user placement", () => {
    const placement = { batch: { id: "b1" }, department: { id: "d1" }, section: { id: "s1" }, cohort: { id: "c1" } };
    assert.deepEqual(selectionFromPlacement(placement), { batch: "b1", department: "d1", section: "s1", cohort: "c1" });
    assert.deepEqual(selectionFromPlacement(null), EMPTY_SELECTION);
  });
});

describe("flatten", () => {
  it("lists every node depth first", () => {
    assert.deepEqual(
      flatten(TREE).map((n) => n.id),
      ["b1", "d1", "s1", "c1", "c2", "d2", "b2"]
    );
  });
});
