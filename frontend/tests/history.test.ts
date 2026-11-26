import { describe, expect, it } from "vitest";
import { History } from "../src/history";

describe("History", () => {
  it("undoes and redoes", () => {
    const h = new History<number>();
    h.push(1, "a", 0);
    h.push(2, "b", 5000);
    expect(h.undo(3)).toBe(2);
    expect(h.undo(2)).toBe(1);
    expect(h.undo(1)).toBeUndefined();
    expect(h.redo(1)).toBe(2);
    expect(h.canRedo).toBe(true);
  });

  it("merges quick edits of the same key and drops redo on a new edit", () => {
    const h = new History<number>();
    h.push(1, "name", 0);
    h.push(2, "name", 100);
    expect(h.undo(3)).toBe(1);
    expect(h.canUndo).toBe(false);
    h.push(9, "x", 9000);
    expect(h.canRedo).toBe(false);
  });

  it("keeps at most 50 steps", () => {
    const h = new History<number>();
    for (let i = 0; i < 60; i++) h.push(i, `k${i}`, i * 5000);
    let n = 0;
    let cur = 60;
    for (let v = h.undo(cur); v !== undefined; v = h.undo(cur)) {
      cur = v;
      n++;
    }
    expect(n).toBe(50);
  });
});
