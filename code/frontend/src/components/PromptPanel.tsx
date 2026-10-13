import { useState } from "react";
import { SCENARIOS, type Scenario } from "../scenarios";

interface Props {
  pending: boolean;
  canSend: boolean;
  onSend: (prompt: string) => void;
  onScenario: (scenario: Scenario) => void;
}

export default function PromptPanel({ pending, canSend, onSend, onScenario }: Props) {
  const [prompt, setPrompt] = useState("");
  const ready = canSend && !pending && prompt.trim() !== "";

  return (
    <section className="panel" aria-labelledby="prompt-title">
      <h2 id="prompt-title">질문 보내기</h2>
      <label className="field">
        <span className="field-label">질문</span>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && ready) {
              onSend(prompt);
            }
          }}
          rows={4}
          placeholder="무엇이든 물어보세요 (Ctrl+Enter로 전송)"
        />
      </label>
      <button type="button" className="primary" disabled={!ready} onClick={() => onSend(prompt)}>
        {pending ? "기다리는 중…" : "보내기"}
      </button>

      <h3>시나리오</h3>
      <div className="chips">
        {SCENARIOS.map((scenario) => (
          <button
            key={scenario.id}
            type="button"
            className="chip"
            disabled={pending || (!canSend && scenario.apiKey === undefined)}
            onClick={() => onScenario(scenario)}
          >
            {scenario.label}
          </button>
        ))}
      </div>
      {!canSend && (
        <p className="hint">키를 입력하면 보낼 수 있습니다. 틀린 키 시나리오는 키 없이도 됩니다.</p>
      )}
    </section>
  );
}
