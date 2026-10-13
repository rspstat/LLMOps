import { describe, expect, it } from "vitest";
import { parseRouteInfo, sendChat } from "./api";

function fakeFetch(response: Response | Error) {
  const calls: { url: string; init: RequestInit }[] = [];
  const impl = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    if (response instanceof Error) throw response;
    return response;
  }) as unknown as typeof fetch;
  return { impl, calls };
}

function ticker(...times: number[]) {
  const queue = [...times];
  return () => queue.shift() ?? 0;
}

const OK_BODY = {
  id: "chatcmpl-abc",
  model: "qwen3.7-flash",
  choices: [{ index: 0, message: { role: "assistant", content: "Paris" }, finish_reason: "stop" }],
  usage: { prompt_tokens: 24, completion_tokens: 1, total_tokens: 25 },
};

const OK_HEADERS = {
  "X-Request-ID": "abc123",
  "X-LLMOps-Route": "small",
  "X-LLMOps-Route-Reason": "judge_easy",
  "X-LLMOps-P-Easy": "1.0000",
  "X-LLMOps-Fallback": "false",
  "X-LLMOps-Cost-USD": "0.00002080",
};

describe("parseRouteInfo", () => {
  it("reads every gateway header", () => {
    const info = parseRouteInfo(new Headers(OK_HEADERS));

    expect(info).toEqual({
      route: "small",
      reason: "judge_easy",
      pEasy: 1,
      fallback: false,
      costUsd: 0.0000208,
    });
  });

  it("treats missing or malformed values as unknown instead of guessing", () => {
    const info = parseRouteInfo(
      new Headers({ "X-LLMOps-Route": "huge", "X-LLMOps-P-Easy": "abc", "X-LLMOps-Cost-USD": "" }),
    );

    expect(info).toEqual({ route: null, reason: null, pEasy: null, fallback: false, costUsd: null });
  });

  it("reports a fallback only for the exact value true", () => {
    expect(parseRouteInfo(new Headers({ "X-LLMOps-Fallback": "true" })).fallback).toBe(true);
    expect(parseRouteInfo(new Headers({ "X-LLMOps-Fallback": "TRUE" })).fallback).toBe(false);
  });
});

describe("sendChat", () => {
  it("posts an OpenAI-style request with the Bearer key and returns the parsed answer", async () => {
    const { impl, calls } = fakeFetch(
      new Response(JSON.stringify(OK_BODY), { status: 200, headers: OK_HEADERS }),
    );

    const outcome = await sendChat("secret-key", "capital of France?", {
      fetchImpl: impl,
      now: ticker(100, 350),
    });

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("/v1/chat/completions");
    const headers = calls[0].init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer secret-key");
    expect(JSON.parse(calls[0].init.body as string)).toEqual({
      messages: [{ role: "user", content: "capital of France?" }],
      max_tokens: 64,
    });
    expect(outcome).toMatchObject({
      ok: true,
      status: 200,
      requestId: "abc123",
      latencyMs: 250,
      content: "Paris",
      model: "qwen3.7-flash",
      promptTokens: 24,
      completionTokens: 1,
    });
    expect(outcome.ok && outcome.info.route).toBe("small");
  });

  it("surfaces the gateway's error code, message and param", async () => {
    const body = {
      error: { message: "messages: List should have at least 1 item", type: "invalid_request_error", param: "messages", code: "invalid_request" },
    };
    const { impl } = fakeFetch(
      new Response(JSON.stringify(body), { status: 422, headers: { "X-Request-ID": "r1" } }),
    );

    const outcome = await sendChat("k", "x", { fetchImpl: impl });

    expect(outcome).toMatchObject({
      ok: false,
      status: 422,
      requestId: "r1",
      code: "invalid_request",
      param: "messages",
    });
  });

  it("reports a 401 without claiming anything about the key", async () => {
    const body = { error: { message: "Invalid or missing API key", type: "invalid_request_error", param: null, code: "invalid_api_key" } };
    const { impl } = fakeFetch(new Response(JSON.stringify(body), { status: 401 }));

    const outcome = await sendChat("wrong", "x", { fetchImpl: impl });

    expect(outcome).toMatchObject({ ok: false, status: 401, code: "invalid_api_key", param: null });
  });

  it("turns a network failure into a failure outcome instead of throwing", async () => {
    const { impl } = fakeFetch(new TypeError("Failed to fetch"));

    const outcome = await sendChat("k", "x", { fetchImpl: impl, now: ticker(0, 12) });

    expect(outcome).toMatchObject({ ok: false, status: 0, code: "network_error", latencyMs: 12 });
  });

  it("handles a non-JSON error page", async () => {
    const { impl } = fakeFetch(new Response("<html>Bad gateway</html>", { status: 502 }));

    const outcome = await sendChat("k", "x", { fetchImpl: impl });

    expect(outcome).toMatchObject({ ok: false, status: 502, code: "invalid_response" });
  });

  it("falls back to a generic code when an error body has no error object", async () => {
    const { impl } = fakeFetch(new Response(JSON.stringify({ detail: "nope" }), { status: 500 }));

    const outcome = await sendChat("k", "x", { fetchImpl: impl });

    expect(outcome).toMatchObject({ ok: false, status: 500, code: "http_error", message: "HTTP 500" });
  });

  it("rejects a 200 response that has no answer", async () => {
    const { impl } = fakeFetch(new Response(JSON.stringify({ choices: [] }), { status: 200 }));

    const outcome = await sendChat("k", "x", { fetchImpl: impl });

    expect(outcome).toMatchObject({ ok: false, status: 200, code: "invalid_response" });
  });

  it("keeps the fallback flag from the headers", async () => {
    const { impl } = fakeFetch(
      new Response(JSON.stringify(OK_BODY), {
        status: 200,
        headers: { ...OK_HEADERS, "X-LLMOps-Fallback": "true" },
      }),
    );

    const outcome = await sendChat("k", "x", { fetchImpl: impl });

    expect(outcome.ok && outcome.info.fallback).toBe(true);
  });
});
