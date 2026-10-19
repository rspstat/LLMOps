import { describe, expect, it } from "vitest";
import { describePipeline } from "./pipeline";
import type { ChatFailure, ChatSuccess } from "./types";

const BASE = { requestId: "r", latencyMs: 420 };

function answered(overrides: Partial<ChatSuccess["info"]> = {}, model = "qwen3.7-flash"): ChatSuccess {
  return {
    ok: true,
    status: 200,
    ...BASE,
    content: "x",
    model,
    promptTokens: 1,
    completionTokens: 1,
    info: { route: "small", reason: "judge_easy", pEasy: 1, fallback: false, costUsd: 0.1, ...overrides },
  };
}

function failed(status: number, code: string): ChatFailure {
  return { ok: false, ...BASE, status, code, message: "m", param: null };
}

const statuses = (view: ReturnType<typeof describePipeline>) => view.nodes.map((n) => n.status);

describe("describePipeline", () => {
  it("shows four idle stages before anything was sent", () => {
    const view = describePipeline(null, false);

    expect(view.nodes.map((n) => n.id)).toEqual(["guard", "router", "model", "response"]);
    expect(statuses(view)).toEqual(["idle", "idle", "idle", "idle"]);
    expect(view.flowing).toBe(false);
    expect(view.notice).toBeNull();
  });

  it("makes the light flow while a request is in flight, whatever came before", () => {
    const view = describePipeline(answered(), true);

    expect(view.flowing).toBe(true);
    expect(statuses(view)).toEqual(["idle", "idle", "idle", "idle"]);
  });

  it("marks every stage ok and names the route, the model and the latency", () => {
    const view = describePipeline(answered({ route: "frontier" }, "qwen3.8-max"), false);

    expect(statuses(view)).toEqual(["ok", "ok", "ok", "ok"]);
    expect(view.nodes[1]).toMatchObject({ caption: "상용 모델", route: "frontier" });
    expect(view.nodes[2]).toMatchObject({ caption: "qwen3.8-max", route: "frontier" });
    expect(view.nodes[3].caption).toBe("420 ms");
    expect(view.detour).toBe(false);
  });

  it("flags the model stage and the detour when another model answered", () => {
    const view = describePipeline(answered({ fallback: true }, "qwen3.8-max"), false);

    expect(statuses(view)).toEqual(["ok", "ok", "warn", "ok"]);
    expect(view.nodes[1].route).toBe("small"); // what the router chose
    expect(view.nodes[2].caption).toBe("qwen3.8-max"); // who actually answered
    expect(view.detour).toBe(true);
  });

  it("does not invent a route when the headers did not carry one", () => {
    const view = describePipeline(answered({ route: null }), false);

    expect(view.nodes[1].caption).toBe("-");
    expect(view.nodes[1].route).toBeUndefined();
  });

  it("stops at the guard for a blocked input", () => {
    const view = describePipeline(failed(400, "input_blocked"), false);

    expect(statuses(view)).toEqual(["error", "skipped", "skipped", "skipped"]);
    expect(view.nodes[0].caption).toBe("차단");
    expect(view.notice).toBeNull();
  });

  it("fails at the model when every provider failed", () => {
    const view = describePipeline(failed(502, "provider_unavailable"), false);

    expect(statuses(view)).toEqual(["ok", "ok", "error", "skipped"]);
  });

  it.each([
    [401, "invalid_api_key"],
    [422, "invalid_request"],
    [404, "not_found"],
  ])("says a %i %s was refused at the door and skips every stage", (status, code) => {
    const view = describePipeline(failed(status, code), false);

    expect(statuses(view)).toEqual(["skipped", "skipped", "skipped", "skipped"]);
    expect(view.notice).toContain("입구에서 거절");
    expect(view.notice).toContain(code);
  });

  it("reports a lost connection differently from a refusal", () => {
    const view = describePipeline(failed(0, "network_error"), false);

    expect(statuses(view)).toEqual(["skipped", "skipped", "skipped", "skipped"]);
    expect(view.notice).toContain("연결하지 못했습니다");
  });

  it("does not call an unexpected server error a refusal at the door", () => {
    const view = describePipeline(failed(500, "internal_error"), false);

    expect(view.notice).toContain("처리 중 오류");
    expect(view.notice).not.toContain("입구");
  });
});
