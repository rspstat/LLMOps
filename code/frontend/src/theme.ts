export type Theme = "light" | "dark";

/** Same key as public/theme-init.js. Only the theme name is stored, never anything sensitive. */
export const THEME_STORAGE_KEY = "llmops-demo-theme";

/** A saved choice wins; otherwise follow the operating system. */
export function resolveTheme(stored: string | null, systemPrefersDark: boolean): Theme {
  if (stored === "light" || stored === "dark") return stored;
  return systemPrefersDark ? "dark" : "light";
}

export function nextTheme(theme: Theme): Theme {
  return theme === "dark" ? "light" : "dark";
}

export function readStoredTheme(storage: Pick<Storage, "getItem"> | null = safeStorage()): string | null {
  try {
    return storage?.getItem(THEME_STORAGE_KEY) ?? null;
  } catch {
    return null;
  }
}

export function storeTheme(theme: Theme, storage: Pick<Storage, "setItem"> | null = safeStorage()): void {
  try {
    storage?.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // blocked storage: the choice just lasts until the page is closed
  }
}

function safeStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}
