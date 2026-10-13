import { formatCost } from "../format";
import type { Summary } from "../summary";

export default function SummaryBar({ summary }: { summary: Summary }) {
  const items: [string, string][] = [
    ["요청", String(summary.total)],
    ["소형 선택", String(summary.small)],
    ["상용 선택", String(summary.frontier)],
    ["차단 (가드)", String(summary.blocked)],
    ["오류", String(summary.failed)],
    ["대체 응답", String(summary.fallbacks)],
    ["토큰 합계", String(summary.totalTokens)],
    ["비용 합계", formatCost(summary.totalCostUsd)],
  ];
  return (
    <ul className="summary" aria-label="요약">
      {items.map(([name, value]) => (
        <li key={name}>
          <span className="summary-value">{value}</span>
          <span className="summary-name">{name}</span>
        </li>
      ))}
    </ul>
  );
}
