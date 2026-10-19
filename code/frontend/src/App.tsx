import { useMemo, useRef, useState, type CSSProperties } from "react";
import { sendChat } from "./api";
import HistoryTable from "./components/HistoryTable";
import { LogoMark } from "./components/Icons";
import KeyField from "./components/KeyField";
import Pipeline from "./components/Pipeline";
import PromptPanel from "./components/PromptPanel";
import ResultCard from "./components/ResultCard";
import SummaryBar from "./components/SummaryBar";
import ThemeToggle from "./components/ThemeToggle";
import { useTheme } from "./hooks/useTheme";
import type { Scenario } from "./scenarios";
import { summarize } from "./summary";
import type { HistoryEntry } from "./types";

export default function App() {
  const [theme, toggleTheme] = useTheme();
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
    <>
      <div className="backdrop" aria-hidden="true">
        <span className="blob blob-a" />
        <span className="blob blob-b" />
        <span className="blob blob-c" />
      </div>
      <main>
        <header className="top">
          <div className="brand">
            <span className="logo">
              <LogoMark />
            </span>
            <div>
              <h1>
                <span className="gradient-text">LLMOps Gateway</span> 데모
              </h1>
              <p className="muted">
                질문 하나가 입력 가드 → 라우팅 → 모델 호출을 거치는 과정을 보여 줍니다. 경로·사유·p(easy)·
                비용은 응답 헤더(<code>X-LLMOps-*</code>)에서 읽습니다.
              </p>
            </div>
          </div>
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
        </header>

        <div className="grid">
          <div className="col" style={{ "--i": 0 } as CSSProperties}>
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
          <div className="col" style={{ "--i": 1 } as CSSProperties}>
            <Pipeline outcome={selected?.outcome ?? null} pending={pending} />
            <ResultCard
              key={selectedId ?? "none"}
              prompt={selected?.prompt ?? null}
              outcome={selected?.outcome ?? null}
              pending={pending}
            />
          </div>
        </div>

        <SummaryBar summary={summary} />
        <HistoryTable entries={history} selectedId={selectedId} onSelect={setSelectedId} />
      </main>
    </>
  );
}
