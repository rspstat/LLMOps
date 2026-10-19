import type { CSSProperties } from "react";
import { formatCost } from "../format";
import type { Summary } from "../summary";
import AnimatedNumber from "./AnimatedNumber";

interface Tile {
  name: string;
  value: number;
  tone: "neutral" | "small" | "frontier" | "warn" | "error";
  format?: (value: number) => string;
}

export default function SummaryBar({ summary }: { summary: Summary }) {
  const tiles: Tile[] = [
    { name: "요청", value: summary.total, tone: "neutral" },
    { name: "소형 선택", value: summary.small, tone: "small" },
    { name: "상용 선택", value: summary.frontier, tone: "frontier" },
    { name: "차단 (가드)", value: summary.blocked, tone: "warn" },
    { name: "오류", value: summary.failed, tone: "error" },
    { name: "대체 응답", value: summary.fallbacks, tone: "warn" },
    { name: "토큰 합계", value: summary.totalTokens, tone: "neutral" },
    { name: "비용 합계", value: summary.totalCostUsd, tone: "neutral", format: formatCost },
  ];
  return (
    <ul className="summary" aria-label="요약">
      {tiles.map((tile, index) => (
        <li key={tile.name} data-tone={tile.tone} style={{ "--i": index } as CSSProperties}>
          <span className="summary-value">
            <AnimatedNumber value={tile.value} format={tile.format} durationMs={600} />
          </span>
          <span className="summary-name">{tile.name}</span>
        </li>
      ))}
    </ul>
  );
}
