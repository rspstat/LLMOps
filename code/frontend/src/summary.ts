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
  }
  return summary;
}
