import { useMemo, useRef, useState } from "react";
import { sendChat } from "./api";
import HistoryTable from "./components/HistoryTable";
import KeyField from "./components/KeyField";
import PromptPanel from "./components/PromptPanel";
import ResultCard from "./components/ResultCard";
import SummaryBar from "./components/SummaryBar";
import type { Scenario } from "./scenarios";
import { summarize } from "./summary";
import type { HistoryEntry } from "./types";

export default function App() {
  const [apiKey, setApiKey] = useState("");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [pending, setPending] = useState(false);
  const nextId = useRef(1);

  const summary = useMemo(() => summarize(history), [history]);
  const selected = history.find((entry) => entry.id === selectedId) ?? null;

  async function submit(prompt: string, key: string) {
    setPending(true);
    const outcome = await sendChat(key, prompt);
    const id = nextId.current++;
    setHistory((entries) => [...entries, { id, prompt, outcome }]);
    setSelectedId(id);
    setPending(false);
  }

  return (
    <main>
      <header>
        <h1>LLMOps Gateway 데모</h1>
        <p className="muted">
          질문 하나가 입력 가드 → 라우팅 → 모델 호출을 거치는 과정을 보여 줍니다. 경로·사유·p(easy)·
          비용은 응답 헤더(<code>X-LLMOps-*</code>)에서 읽습니다.
        </p>
      </header>

      <div className="grid">
        <div>
          <KeyField value={apiKey} onChange={setApiKey} />
          <PromptPanel
            pending={pending}
            canSend={apiKey !== ""}
            onSend={(prompt) => void submit(prompt, apiKey)}
            onScenario={(scenario: Scenario) =>
              void submit(scenario.prompt, scenario.apiKey ?? apiKey)
            }
          />
        </div>
        <ResultCard prompt={selected?.prompt ?? null} outcome={selected?.outcome ?? null} />
      </div>

      <SummaryBar summary={summary} />
      <HistoryTable entries={history} selectedId={selectedId} onSelect={setSelectedId} />
    </main>
  );
}
