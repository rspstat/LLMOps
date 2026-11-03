import type { HistoryEntry } from "./types";

export interface Summary {
  total: number;
  answered: number;
  blocked: number; // refused by the input guard
  failed: number; // any other error (auth, validation, upstream, network)
  small: number; // answered requests the router sent to the small model
  frontier: number;
  fallbacks: number;
  totalCostUsd: number;
  totalTokens: number;
  /** What the answered requests would have cost on the frontier model alone (only requests that
   *  report both a baseline and an actual cost are compared). */
  baselineUsd: number;
  /** baselineUsd minus the actual cost of the same requests; negative when the judge call cost
   *  more than routing saved. */
  savedUsd: number;
  /** savedUsd / baselineUsd, or null when no request could be compared. */
  savedRate: number | null;
}

/** Totals for the session table. `small`/`frontier` count the router's choice, not who answered. */
export function summarize(entries: readonly HistoryEntry[]): Summary {
  const summary: Summary = {
    total: entries.length,
    answered: 0,
    blocked: 0,
    failed: 0,
    small: 0,
    frontier: 0,
    fallbacks: 0,
    totalCostUsd: 0,
    totalTokens: 0,
    baselineUsd: 0,
    savedUsd: 0,
    savedRate: null,
  };
  for (const { outcome } of entries) {
    if (!outcome.ok) {
      if (outcome.code === "input_blocked") summary.blocked += 1;
      else summary.failed += 1;
      continue;
    }
    summary.answered += 1;
    if (outcome.info.route === "small") summary.small += 1;
    if (outcome.info.route === "frontier") summary.frontier += 1;
    if (outcome.info.fallback) summary.fallbacks += 1;
    summary.totalCostUsd += outcome.info.costUsd ?? 0;
    summary.totalTokens += outcome.promptTokens + outcome.completionTokens;
    const { baselineUsd, costUsd } = outcome.info;
    if (baselineUsd !== null && costUsd !== null) {
      summary.baselineUsd += baselineUsd;
      summary.savedUsd += baselineUsd - costUsd;
    }
  }
  summary.savedRate = summary.baselineUsd > 0 ? summary.savedUsd / summary.baselineUsd : null;
  return summary;
}
