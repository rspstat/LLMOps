import { describe, expect, it } from "vitest";
import { summarize } from "./summary";
import type { ChatOutcome, HistoryEntry, Route } from "./types";

const BASE = { status: 200, requestId: "r", latencyMs: 10 };

function answered(
  route: Route,
  overrides: { fallback?: boolean; costUsd?: number | null; tokens?: [number, number] } = {},
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
});
