import { useCallback, useEffect, useState } from "react";
import { nextTheme, readStoredTheme, resolveTheme, storeTheme, type Theme } from "../theme";

const DARK_QUERY = "(prefers-color-scheme: dark)";

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia(DARK_QUERY).matches;
}

/** The theme in effect, a toggle, and live following of the OS setting until the user chooses. */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => resolveTheme(readStoredTheme(), systemPrefersDark()));

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  useEffect(() => {
    const query = window.matchMedia(DARK_QUERY);
    const follow = () => {
      if (readStoredTheme() === null) setTheme(resolveTheme(null, query.matches));
    };
    query.addEventListener("change", follow);
    return () => query.removeEventListener("change", follow);
  }, []);

  const toggle = useCallback(() => {
    setTheme((current) => {
      const next = nextTheme(current);
      storeTheme(next);
      return next;
    });
  }, []);

  return [theme, toggle];
}
