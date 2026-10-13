import { formatCost, formatLatency, formatPEasy, ROUTE_LABEL } from "../format";
import type { HistoryEntry } from "../types";

interface Props {
  entries: readonly HistoryEntry[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

function shorten(text: string, max = 40): string {
  const flat = text.trim() === "" ? "(공백)" : text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max)}…` : flat;
}

export default function HistoryTable({ entries, selectedId, onSelect }: Props) {
  return (
    <section className="panel wide" aria-labelledby="history-title">
      <h2 id="history-title">이번 접속의 요청</h2>
      {entries.length === 0 ? (
        <p className="hint">
          아직 보낸 요청이 없습니다. 이 목록은 새로고침하면 사라지며 서버에 저장되지 않습니다.
        </p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>질문</th>
                <th>결과</th>
                <th>경로</th>
                <th>p(easy)</th>
                <th>모델</th>
                <th>비용</th>
                <th>지연</th>
              </tr>
            </thead>
            <tbody>
              {[...entries].reverse().map(({ id, prompt, outcome }) => (
                <tr
                  key={id}
                  className={id === selectedId ? "selected" : undefined}
                  onClick={() => onSelect(id)}
                >
                  <td>{id}</td>
                  <td>{shorten(prompt)}</td>
                  <td>{outcome.ok ? "200" : `${outcome.status || "-"} ${outcome.code}`}</td>
                  <td>
                    {outcome.ok && outcome.info.route
                      ? ROUTE_LABEL[outcome.info.route] + (outcome.info.fallback ? " ⚠" : "")
                      : "-"}
                  </td>
                  <td>{outcome.ok ? formatPEasy(outcome.info.pEasy) : "-"}</td>
                  <td>{outcome.ok ? outcome.model : "-"}</td>
                  <td>{outcome.ok ? formatCost(outcome.info.costUsd) : "-"}</td>
                  <td>{formatLatency(outcome.latencyMs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
