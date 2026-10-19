import type { CSSProperties, ReactNode } from "react";
import { describePipeline, type NodeId, type NodeStatus } from "../pipeline";
import type { ChatOutcome } from "../types";
import { AlertIcon, CheckIcon, ChipIcon, CrossIcon, ReplyIcon, RouteIcon, ShieldIcon } from "./Icons";

const ICONS: Record<NodeId, ReactNode> = {
  guard: <ShieldIcon />,
  router: <RouteIcon />,
  model: <ChipIcon />,
  response: <ReplyIcon />,
};

const BADGES: Partial<Record<NodeStatus, ReactNode>> = {
  ok: <CheckIcon />,
  warn: <AlertIcon />,
  error: <CrossIcon />,
};

interface Props {
  outcome: ChatOutcome | null;
  pending: boolean;
}

/** The four stages a request passes. While waiting, light runs along the line; afterwards the
 *  stages show what actually happened (passed, blocked, answered by another model...). */
export default function Pipeline({ outcome, pending }: Props) {
  const view = describePipeline(outcome, pending);
  const flow = view.flowing ? "flowing" : "still";

  return (
    <section className="pipeline-wrap" aria-label="요청이 지나간 단계">
      <ol className={`pipeline ${flow}${view.detour ? " detour" : ""}`}>
        {view.nodes.map((node, index) => (
          <li
            key={node.id}
            className="node"
            data-status={node.status}
            data-route={node.route}
            style={{ "--i": index } as CSSProperties}
          >
            <span className="node-icon">
              {ICONS[node.id]}
              {BADGES[node.status] && <span className="node-badge">{BADGES[node.status]}</span>}
            </span>
            <span className="node-label">{node.label}</span>
            <span className="node-caption">{node.caption}</span>
          </li>
        ))}
      </ol>
      {view.detour && <p className="pipeline-note warn">라우터가 고른 모델이 실패해 다른 모델이 대신 답했습니다.</p>}
      {view.notice && <p className="pipeline-note error">{view.notice}</p>}
    </section>
  );
}
