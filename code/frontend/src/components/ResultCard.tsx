import type { ReactNode } from "react";
import { describeReason, formatCost, formatLatency, formatPEasy, ROUTE_LABEL } from "../format";
import type { ChatOutcome } from "../types";

interface Props {
  prompt: string | null;
  outcome: ChatOutcome | null;
}

function Row({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className="row">
      <dt>{name}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export default function ResultCard({ prompt, outcome }: Props) {
  if (outcome === null || prompt === null) {
    return (
      <section className="panel" aria-labelledby="result-title">
        <h2 id="result-title">결과</h2>
        <p className="hint">질문을 보내면 게이트웨이가 무엇을 했는지 여기에 표시됩니다.</p>
      </section>
    );
  }

  // Everything below is rendered as text. Model output and error messages are untrusted.
  return (
    <section className="panel" aria-labelledby="result-title" aria-live="polite">
      <h2 id="result-title">결과</h2>
      <p className="prompt-echo">{prompt.trim() === "" ? "(공백 입력)" : prompt}</p>

      {outcome.ok ? (
        <>
          <p className="answer">{outcome.content === "" ? "(빈 답변)" : outcome.content}</p>
          <div className="badges">
            {outcome.info.route && (
              <span className={`badge route-${outcome.info.route}`}>
                라우터 선택: {ROUTE_LABEL[outcome.info.route]}
              </span>
            )}
            {outcome.info.fallback && (
              <span className="badge warn">장애로 다른 모델이 대신 답함</span>
            )}
          </div>
          <dl>
            <Row name="사유">{describeReason(outcome.info.reason)}</Row>
            <Row name="p(easy)">
              {outcome.info.pEasy === null ? (
                <span className="muted">판정기를 거치지 않음 (규칙 모드이거나 규칙이 먼저 확정)</span>
              ) : (
                <>
                  <span className="bar" aria-hidden="true">
                    <span style={{ width: `${Math.round(outcome.info.pEasy * 100)}%` }} />
                  </span>{" "}
                  {formatPEasy(outcome.info.pEasy)}
                </>
              )}
            </Row>
            <Row name="답한 모델">{outcome.model}</Row>
            <Row name="토큰">
              입력 {outcome.promptTokens} / 출력 {outcome.completionTokens}
            </Row>
            <Row name="비용">{formatCost(outcome.info.costUsd)}</Row>
            <Row name="지연">{formatLatency(outcome.latencyMs)}</Row>
            <Row name="요청 ID">
              <code>{outcome.requestId ?? "-"}</code>
            </Row>
          </dl>
        </>
      ) : (
        <>
          <p className="answer error">
            {outcome.status === 0 ? "연결 실패" : `HTTP ${outcome.status}`} · {outcome.code}
          </p>
          <p>{outcome.message}</p>
          <dl>
            {outcome.param && (
              <Row name="필드">
                <code>{outcome.param}</code>
              </Row>
            )}
            <Row name="지연">{formatLatency(outcome.latencyMs)}</Row>
            <Row name="요청 ID">
              <code>{outcome.requestId ?? "-"}</code>
            </Row>
          </dl>
        </>
      )}
    </section>
  );
}
