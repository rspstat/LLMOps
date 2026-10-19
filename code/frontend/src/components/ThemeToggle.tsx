import type { Theme } from "../theme";
import { MoonIcon, SunIcon } from "./Icons";

interface Props {
  theme: Theme;
  onToggle: () => void;
}

export default function ThemeToggle({ theme, onToggle }: Props) {
  const dark = theme === "dark";
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={onToggle}
      aria-label={dark ? "라이트 모드로 전환" : "다크 모드로 전환"}
      aria-pressed={dark}
      title={dark ? "라이트 모드" : "다크 모드"}
    >
      <span className="theme-icon sun">
        <SunIcon />
      </span>
      <span className="theme-icon moon">
        <MoonIcon />
      </span>
    </button>
  );
}
