import type { ReactNode } from "react";
import { useTypewriter } from "../hooks/useTypewriter";
import { describeReason, formatCost, formatLatency, ROUTE_LABEL } from "../format";
import type { ChatFailure, ChatSuccess } from "../types";
import AnimatedNumber from "./AnimatedNumber";
import Gauge from "./Gauge";
import { AlertIcon } from "./Icons";

function Row({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className="row">
      <dt>{name}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="skeleton" aria-hidden="true">
      <span className="bar-line w-70" />
      <span className="bar-line w-40" />
      <span className="bar-line w-90" />
      <span className="bar-line w-55" />
    </div>
  );
}

function Answer({ text }: { text: string }) {
  const { shown, done } = useTypewriter(text);
  return (
    <p className="answer">
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">
        {shown}
        {!done && <span className="caret" />}
      </span>
    </p>
  );
}

function Success({ outcome }: { outcome: ChatSuccess }) {
  const { info } = outcome;
  return (
    <>
      {outcome.content === "" ? <p className="answer muted">(빈 답변)</p> : <Answer text={outcome.content} />}
      <div className="badges">
        {info.route && (
          <span className={`badge route-${info.route}`}>라우터 선택 · {ROUTE_LABEL[info.route]}</span>
        )}
        {info.fallback && (
          <span className="badge warn">
            <AlertIcon /> 장애로 다른 모델이 대신 답함
          </span>
        )}
      </div>
      <dl>
        <Row name="사유">{describeReason(info.reason)}</Row>
        <Row name="p(easy)">
          {info.pEasy === null ? (
            <span className="muted">판정기를 거치지 않음 (규칙 모드이거나 규칙이 먼저 확정)</span>
          ) : (
            <Gauge value={info.pEasy} />
          )}
        </Row>
        <Row name="답한 모델">{outcome.model}</Row>
        <Row name="토큰">
          입력 <AnimatedNumber value={outcome.promptTokens} /> / 출력{" "}
          <AnimatedNumber value={outcome.completionTokens} />
        </Row>
        <Row name="비용">
          {info.costUsd === null ? "-" : <AnimatedNumber value={info.costUsd} format={formatCost} />}
        </Row>
        <Row name="지연">
          <AnimatedNumber value={outcome.latencyMs} format={(v) => formatLatency(Math.round(v))} />
        </Row>
        <Row name="요청 ID">
          <code>{outcome.requestId ?? "-"}</code>
        </Row>
      </dl>
    </>
  );
}

function Failure({ outcome }: { outcome: ChatFailure }) {
  return (
    <>
      <p className="answer error">
        {outcome.status === 0 ? "연결 실패" : `HTTP ${outcome.status}`} · {outcome.code}
      </p>
      <p className="error-message">{outcome.message}</p>
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
  );
}

interface Props {
  prompt: string | null;
  outcome: ChatSuccess | ChatFailure | null;
  pending: boolean;
}

/** Everything is rendered as text: model output and error messages are untrusted. Give this
 *  component a new `key` per request so the typing and counting restart. */
export default function ResultCard({ prompt, outcome, pending }: Props) {
  return (
    <section className="panel result" aria-labelledby="result-title" aria-live="polite" aria-busy={pending}>
      <h2 id="result-title">결과</h2>
      {pending ? (
        <Skeleton />
      ) : outcome === null || prompt === null ? (
        <p className="hint">질문을 보내면 게이트웨이가 무엇을 했는지 여기에 표시됩니다.</p>
      ) : (
        <div className={outcome.ok ? "result-body" : "result-body failed"}>
          <p className="prompt-echo">{prompt.trim() === "" ? "(공백 입력)" : prompt}</p>
          {outcome.ok ? <Success outcome={outcome} /> : <Failure outcome={outcome} />}
        </div>
      )}
    </section>
  );
}
