import { useEffect, useState } from "react";
import { formatPercent, formatSaved } from "../format";
import type { Summary } from "../summary";
import AnimatedNumber from "./AnimatedNumber";

/** How much routing saved, against sending every answered request to the frontier model.
 *  The two bars show the frontier-only cost (full width) and what was actually spent. */
export default function SavingsCard({ summary }: { summary: Summary }) {
  const comparable = summary.savedRate !== null;
  const actual = summary.baselineUsd - summary.savedUsd;
  const actualShare = comparable && summary.baselineUsd > 0 ? Math.min(1, Math.max(0, actual / summary.baselineUsd)) : 0;

  // widths start at 0 so they grow when the numbers first appear
  const [grown, setGrown] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setGrown(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  const tone = !comparable ? "empty" : summary.savedUsd >= 0 ? "positive" : "negative";
  return (
    <section className="savings" data-tone={tone} aria-labelledby="savings-title">
      <div className="savings-main">
        <h2 id="savings-title">아낀 금액</h2>
        <p className="savings-value">
          {comparable ? (
            <AnimatedNumber value={summary.savedUsd} format={formatSaved} durationMs={900} />
          ) : (
            "-"
          )}
          {comparable && summary.savedRate !== null && (
            <span className="savings-rate">
              <AnimatedNumber value={summary.savedRate} format={formatPercent} durationMs={900} />
            </span>
          )}
        </p>
        <p className="muted savings-note">
          {comparable
            ? "모든 요청을 상용 모델로만 보냈다면 들었을 비용에서, 판정 비용을 포함한 실제 비용을 뺀 값입니다. 같은 토큰 수로 계산한 추정치입니다."
            : summary.answered === 0
              ? "요청을 보내면 상용 모델만 썼을 때와 비교한 절감액이 여기에 표시됩니다."
              : "상용 모델 단가(FRONTIER_PRICE_*)가 설정되지 않아 절감액을 계산할 수 없습니다."}
        </p>
      </div>
      {comparable && (
        <div className="savings-bars" aria-hidden="true">
          <div className="savings-bar">
            <span className="savings-bar-label">상용만 썼다면</span>
            <span className="savings-track">
              <span className="savings-fill baseline" style={{ width: grown ? "100%" : "0%" }} />
            </span>
            <span className="savings-bar-value">{formatSaved(summary.baselineUsd)}</span>
          </div>
          <div className="savings-bar">
            <span className="savings-bar-label">실제</span>
            <span className="savings-track">
              <span className="savings-fill actual" style={{ width: grown ? `${actualShare * 100}%` : "0%" }} />
            </span>
            <span className="savings-bar-value">{formatSaved(actual)}</span>
          </div>
        </div>
      )}
    </section>
  );
}
