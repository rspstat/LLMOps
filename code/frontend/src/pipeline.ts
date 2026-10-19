import { ROUTE_LABEL } from "./format";
import type { ChatOutcome, Route } from "./types";

export type NodeId = "guard" | "router" | "model" | "response";
export type NodeStatus = "idle" | "ok" | "warn" | "error" | "skipped";

export interface PipelineNode {
  id: NodeId;
  label: string;
  status: NodeStatus;
  caption: string;
  /** Which model route the router picked; only set on the router and model nodes. */
  route?: Route;
}

export interface PipelineView {
  nodes: PipelineNode[];
  /** A request is in flight: the light travels along the line. */
  flowing: boolean;
  /** A different provider answered than the router chose. */
  detour: boolean;
  /** Said under the line when the request never reached the pipeline stages. */
  notice: string | null;
}

const LABELS: Record<NodeId, string> = {
  guard: "입력 가드",
  router: "라우터",
  model: "모델",
  response: "응답",
};
const ORDER: NodeId[] = ["guard", "router", "model", "response"];
const IDLE_CAPTIONS: Record<NodeId, string> = {
  guard: "입력 검사",
  router: "경로 선택",
  model: "모델 호출",
  response: "답변",
};

/** Refused at the gateway's door, before the guard ever looked at the text. */
const EDGE_CODES = new Set(["invalid_api_key", "invalid_request", "not_found", "method_not_allowed"]);

function build(
  statuses: Partial<Record<NodeId, NodeStatus>>,
  captions: Partial<Record<NodeId, string>>,
  extra: Partial<Pick<PipelineView, "flowing" | "detour" | "notice">> = {},
  route?: Route,
): PipelineView {
  return {
    nodes: ORDER.map((id) => ({
      id,
      label: LABELS[id],
      status: statuses[id] ?? "idle",
      caption: captions[id] ?? IDLE_CAPTIONS[id],
      ...(route && (id === "router" || id === "model") ? { route } : {}),
    })),
    flowing: extra.flowing ?? false,
    detour: extra.detour ?? false,
    notice: extra.notice ?? null,
  };
}

/** What each stage of the gateway looked like for this request, for the animated diagram. */
export function describePipeline(outcome: ChatOutcome | null, pending: boolean): PipelineView {
  if (pending) return build({}, {}, { flowing: true });
  if (outcome === null) return build({}, {});

  if (outcome.ok) {
    const { info } = outcome;
    return build(
      {
        guard: "ok",
        router: "ok",
        model: info.fallback ? "warn" : "ok",
        response: "ok",
      },
      {
        guard: "통과",
        router: info.route ? ROUTE_LABEL[info.route] : "-",
        model: outcome.model,
        response: `${outcome.latencyMs} ms`,
      },
      { detour: info.fallback },
      info.route ?? undefined,
    );
  }

  if (outcome.code === "input_blocked") {
    return build(
      { guard: "error", router: "skipped", model: "skipped", response: "skipped" },
      { guard: "차단", router: "-", model: "-", response: "-" },
    );
  }
  if (outcome.code === "provider_unavailable") {
    return build(
      { guard: "ok", router: "ok", model: "error", response: "skipped" },
      { guard: "통과", router: "-", model: "모두 실패", response: "-" },
    );
  }
  const reachedGateway = outcome.status !== 0;
  const edge = EDGE_CODES.has(outcome.code) || !reachedGateway;
  return build(
    { guard: "skipped", router: "skipped", model: "skipped", response: "skipped" },
    { guard: "-", router: "-", model: "-", response: "-" },
    {
      notice: edge
        ? reachedGateway
          ? `게이트웨이 입구에서 거절됨 (${outcome.code})`
          : "게이트웨이에 연결하지 못했습니다"
        : `처리 중 오류 (${outcome.code})`,
    },
  );
}
