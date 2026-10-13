export function formatCost(usd: number | null): string {
  return usd === null ? "-" : `$${usd.toFixed(6)}`;
}

export function formatPEasy(p: number | null): string {
  return p === null ? "-" : p.toFixed(4);
}

export function formatLatency(ms: number): string {
  return `${ms} ms`;
}

const REASONS: Record<string, string> = {
  judge_easy: "판정기가 쉬운 질문으로 판단해 소형 모델로 보냄",
  judge_hard: "판정기가 어려운 질문으로 판단해 상용 모델로 보냄",
  promoted_low_confidence: "판정은 쉬움이지만 확신이 임계값 미만이라 상용 모델로 승격",
  judge_unavailable: "판정기 호출이 실패해 규칙 결과를 사용",
  keyword: "어려운 작업 키워드가 있어 상용 모델로 보냄",
  long_prompt: "프롬프트가 길어 상용 모델로 보냄",
  default_small: "규칙에 걸리지 않아 기본값인 소형 모델로 보냄",
};

export function describeReason(reason: string | null): string {
  if (reason === null) return "-";
  return REASONS[reason] ?? reason;
}

export const ROUTE_LABEL = { small: "소형 모델", frontier: "상용 모델" } as const;
