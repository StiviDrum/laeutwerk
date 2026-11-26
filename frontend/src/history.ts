/** Undo/redo stack of editor drafts (max 50 steps); quick edits of the same field merge. */
export class History<T> {
  private past: T[] = [];
  private future: T[] = [];
  private lastKey = "";
  private lastAt = 0;

  constructor(
    private readonly limit = 50,
    private readonly mergeMs = 800,
  ) {}

  get canUndo(): boolean {
    return this.past.length > 0;
  }

  get canRedo(): boolean {
    return this.future.length > 0;
  }

  clear(): void {
    this.past = [];
    this.future = [];
    this.lastKey = "";
  }

  /** Remember `previous` before a change; same key within mergeMs counts as one step. */
  push(previous: T, key: string, now = Date.now()): void {
    const merge = key === this.lastKey && now - this.lastAt < this.mergeMs && this.past.length > 0;
    this.lastKey = key;
    this.lastAt = now;
    this.future = [];
    if (merge) return;
    this.past.push(previous);
    if (this.past.length > this.limit) this.past.shift();
  }

  undo(current: T): T | undefined {
    const prev = this.past.pop();
    if (prev === undefined) return undefined;
    this.future.push(current);
    this.lastKey = "";
    return prev;
  }

  redo(current: T): T | undefined {
    const next = this.future.pop();
    if (next === undefined) return undefined;
    this.past.push(current);
    this.lastKey = "";
    return next;
  }
}
