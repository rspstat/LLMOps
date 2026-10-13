interface Props {
  value: string;
  onChange: (value: string) => void;
}

/** The key lives only in React state: not in storage, the URL, or a file. */
export default function KeyField({ value, onChange }: Props) {
  return (
    <label className="field">
      <span className="field-label">게이트웨이 키 (GATEWAY_API_KEY)</span>
      <input
        type="password"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete="off"
        spellCheck={false}
        placeholder="새로고침하면 지워집니다"
      />
    </label>
  );
}
