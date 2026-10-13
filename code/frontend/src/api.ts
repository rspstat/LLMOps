import type { ChatOutcome, Route, RouteInfo } from "./types";

const CHAT_URL = "/v1/chat/completions";
const DEMO_MAX_TOKENS = 64; // keeps a demo request cheap

export interface SendOptions {
  fetchImpl?: typeof fetch;
  now?: () => number;
  signal?: AbortSignal;
}

function parseNumber(value: string | null): number | null {
  if (value === null || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function parseRouteInfo(headers: Headers): RouteInfo {
  const route = headers.get("X-LLMOps-Route");
  return {
    route: route === "small" || route === "frontier" ? (route as Route) : null,
    reason: headers.get("X-LLMOps-Route-Reason"),
    pEasy: parseNumber(headers.get("X-LLMOps-P-Easy")),
    fallback: headers.get("X-LLMOps-Fallback") === "true",
    costUsd: parseNumber(headers.get("X-LLMOps-Cost-USD")),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function failure(
  base: { status: number; requestId: string | null; latencyMs: number },
  code: string,
  message: string,
  param: string | null = null,
): ChatOutcome {
  return { ok: false, ...base, code, message, param };
}

/** Send one chat request. Never throws: every problem comes back as a `ChatFailure`. */
export async function sendChat(
  apiKey: string,
  prompt: string,
  options: SendOptions = {},
): Promise<ChatOutcome> {
  const doFetch = options.fetchImpl ?? fetch;
  const now = options.now ?? (() => performance.now());
  const started = now();

  let response: Response;
  try {
    response = await doFetch(CHAT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
      body: JSON.stringify({
        messages: [{ role: "user", content: prompt }],
        max_tokens: DEMO_MAX_TOKENS,
      }),
      signal: options.signal,
    });
  } catch {
    const base = { status: 0, requestId: null, latencyMs: Math.round(now() - started) };
    return failure(base, "network_error", "寃뚯씠?몄썾?댁뿉 ?곌껐?섏? 紐삵뻽?듬땲??");
  }

  const base = {
    status: response.status,
    requestId: response.headers.get("X-Request-ID"),
    latencyMs: Math.round(now() - started),
  };

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return failure(base, "invalid_response", "寃뚯씠?몄썾?댁쓽 ?묐떟???댁꽍?섏? 紐삵뻽?듬땲??");
  }

  if (!response.ok) {
    const error = isRecord(body) && isRecord(body.error) ? body.error : null;
    return failure(
      base,
      typeof error?.code === "string" ? error.code : "http_error",
      typeof error?.message === "string" ? error.message : `HTTP ${response.status}`,
      typeof error?.param === "string" ? error.param : null,
    );
  }

  if (!isRecord(body)) {
    return failure(base, "invalid_response", "?묐떟???듬????놁뒿?덈떎.");
  }
  const choice = Array.isArray(body.choices) ? body.choices[0] : null;
  const message = isRecord(choice) && isRecord(choice.message) ? choice.message : null;
  if (!message || typeof message.content !== "string") {
    return failure(base, "invalid_response", "?묐떟???듬????놁뒿?덈떎.");
  }
  const usage = isRecord(body.usage) ? body.usage : null;

  return {
    ok: true,
    ...base,
    content: message.content,
    model: typeof body.model === "string" ? body.model : "?",
    promptTokens: typeof usage?.prompt_tokens === "number" ? usage.prompt_tokens : 0,
    completionTokens: typeof usage?.completion_tokens === "number" ? usage.completion_tokens : 0,
    info: parseRouteInfo(response.headers),
  };
}
