export type Route = "small" | "frontier";

/** What the gateway says about its own decision, read from the `X-LLMOps-*` response headers. */
export interface RouteInfo {
  route: Route | null; // what the router chose
  reason: string | null; // category only, e.g. "judge_easy" or "keyword"
  pEasy: number | null; // only when a judge was consulted
  fallback: boolean; // true when a different provider answered than the router chose
  costUsd: number | null; // judge call + every provider attempt
}

interface OutcomeBase {
  status: number; // 0 = the request never got an HTTP response
  requestId: string | null;
  latencyMs: number;
}

export interface ChatSuccess extends OutcomeBase {
  ok: true;
  content: string;
  model: string;
  promptTokens: number;
  completionTokens: number;
  info: RouteInfo;
}

export interface ChatFailure extends OutcomeBase {
  ok: false;
  code: string; // the gateway's `error.code`, or a client-side code such as "network_error"
  message: string;
  param: string | null;
}

export type ChatOutcome = ChatSuccess | ChatFailure;

export interface HistoryEntry {
  id: number;
  prompt: string;
  outcome: ChatOutcome;
}
