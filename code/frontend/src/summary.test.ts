import { describe, expect, it } from "vitest";
import { summarize } from "./summary";
import type { ChatOutcome, HistoryEntry, Route } from "./types";

const BASE = { status: 200, requestId: "r", latencyMs: 10 };

function answered(
  route: Route,
  overrides: {
    fallback?: boolean;
    costUsd?: number | null;
    baselineUsd?: number | null;
    tokens?: [number, number];
  } = {},
): ChatOutcome {
  const [promptTokens, completionTokens] = overrides.tokens ?? [10, 1];
  return {
    ok: true,
    ...BASE,
    content: "x",
    model: "m",
    promptTokens,
    completionTokens,
    info: {
      route,
      reason: null,
      pEasy: null,
      fallback: overrides.fallback ?? false,
      costUsd: overrides.costUsd === undefined ? 0.5 : overrides.costUsd,
      baselineUsd: overrides.baselineUsd === undefined ? null : overrides.baselineUsd,
    },
  };
}

function failed(status: number, code: string): ChatOutcome {
  return { ok: false, ...BASE, status, code, message: "m", param: null };
}

function entries(...outcomes: ChatOutcome[]): HistoryEntry[] {
  return outcomes.map((outcome, index) => ({ id: index + 1, prompt: "p", outcome }));
}

describe("summarize", () => {
  it("is all zeros for an empty session", () => {
    expect(summarize([])).toEqual({
      total: 0,
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
    });
  });

  it("counts the router's choice, guard blocks and other errors separately", () => {
    const summary = summarize(
      entries(
        answered("small"),
        answered("small"),
        answered("frontier"),
        failed(400, "input_blocked"),
        failed(401, "invalid_api_key"),
        failed(0, "network_error"),
      ),
    );

    expect(summary).toMatchObject({
      total: 6,
      answered: 3,
      small: 2,
      frontier: 1,
      blocked: 1,
      failed: 2,
    });
  });

  it("sums cost and tokens over answered requests only, and counts fallbacks", () => {
    const summary = summarize(
      entries(
        answered("small", { costUsd: 0.25, tokens: [20, 2] }),
        answered("frontier", { costUsd: 1, fallback: true, tokens: [30, 3] }),
        answered("small", { costUsd: null }),
        failed(502, "provider_unavailable"),
      ),
    );

    expect(summary.totalCostUsd).toBeCloseTo(1.25);
    expect(summary.totalTokens).toBe(22 + 33 + 11);
    expect(summary.fallbacks).toBe(1);
  });

  it("adds up what routing saved against the frontier-only baseline", () => {
    const summary = summarize(
      entries(
        answered("small", { costUsd: 0.1, baselineUsd: 1 }), // saved 0.9
        answered("frontier", { costUsd: 1.1, baselineUsd: 1 }), // the judge made it cost 0.1 more
        answered("small", { costUsd: 0.2, baselineUsd: 2 }), // saved 1.8
      ),
    );

    expect(summary.baselineUsd).toBeCloseTo(4);
    expect(summary.savedUsd).toBeCloseTo(0.9 - 0.1 + 1.8);
    expect(summary.savedRate).toBeCloseTo(2.6 / 4);
  });

  it("compares only requests that report both numbers and never divides by zero", () => {
    const partly = summarize(
      entries(
        answered("small", { costUsd: 0.1, baselineUsd: 1 }),
        answered("small", { costUsd: 0.1, baselineUsd: null }), // no frontier price configured
        answered("small", { costUsd: null, baselineUsd: 1 }), // no cost reported
        failed(400, "input_blocked"),
      ),
    );

    expect(partly.baselineUsd).toBe(1);
    expect(partly.savedUsd).toBeCloseTo(0.9);

    const none = summarize(entries(answered("small", { costUsd: 0.1, baselineUsd: null })));
    expect(none.savedRate).toBeNull();
    expect(none.savedUsd).toBe(0);
  });

  it("reports a negative saving when the judge cost more than it saved", () => {
    const summary = summarize(entries(answered("frontier", { costUsd: 1.2, baselineUsd: 1 })));

    expect(summary.savedUsd).toBeCloseTo(-0.2);
    expect(summary.savedRate).toBeCloseTo(-0.2);
  });
});
