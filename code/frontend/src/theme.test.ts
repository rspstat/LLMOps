import { describe, expect, it } from "vitest";
import script from "../public/theme-init.js?raw";
import { nextTheme, readStoredTheme, resolveTheme, storeTheme, THEME_STORAGE_KEY } from "./theme";

describe("resolveTheme", () => {
  it("lets a saved choice win over the system setting", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("follows the system when nothing valid is saved", () => {
    expect(resolveTheme(null, true)).toBe("dark");
    expect(resolveTheme(null, false)).toBe("light");
    expect(resolveTheme("sepia", true)).toBe("dark");
    expect(resolveTheme("", false)).toBe("light");
  });

  it("toggles between the two themes", () => {
    expect(nextTheme("light")).toBe("dark");
    expect(nextTheme("dark")).toBe("light");
  });
});

describe("theme storage", () => {
  it("reads and writes under one key", () => {
    const data = new Map<string, string>();
    const storage = {
      getItem: (key: string) => data.get(key) ?? null,
      setItem: (key: string, value: string) => void data.set(key, value),
    };

    expect(readStoredTheme(storage)).toBeNull();
    storeTheme("dark", storage);

    expect(data.get(THEME_STORAGE_KEY)).toBe("dark");
    expect(readStoredTheme(storage)).toBe("dark");
  });

  it("survives blocked storage instead of throwing", () => {
    const blocked = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    };

    expect(readStoredTheme(blocked)).toBeNull();
    expect(() => storeTheme("light", blocked)).not.toThrow();
    expect(readStoredTheme(null)).toBeNull();
  });
});

// public/theme-init.js runs before the page paints and cannot import resolveTheme, so this runs
// the real file (imported as raw text) against fake browser globals to keep the two in agreement.
describe("public/theme-init.js", () => {
  function themeSetBy({
    stored,
    dark,
    storageThrows = false,
  }: {
    stored: string | null;
    dark: boolean;
    storageThrows?: boolean;
  }): string | null {
    let applied: string | null = null;
    const fakeWindow = {
      localStorage: {
        getItem: (key: string) => {
          if (storageThrows) throw new Error("blocked");
          return key === THEME_STORAGE_KEY ? stored : null;
        },
      },
      matchMedia: () => ({ matches: dark }),
    };
    const fakeDocument = {
      documentElement: { setAttribute: (_name: string, value: string) => (applied = value) },
    };
    // The script only touches `window` and `document`, so a function with those two parameters
    // runs it exactly as the browser would.
    new Function("window", "document", script)(fakeWindow, fakeDocument);
    return applied;
  }

  it("agrees with resolveTheme for every combination", () => {
    for (const stored of [null, "light", "dark", "junk"]) {
      for (const dark of [true, false]) {
        expect(themeSetBy({ stored, dark }), `${stored} / system dark=${dark}`).toBe(
          resolveTheme(stored, dark),
        );
      }
    }
  });

  it("falls back to the system setting when storage is blocked", () => {
    expect(themeSetBy({ stored: "light", dark: true, storageThrows: true })).toBe("dark");
    expect(themeSetBy({ stored: "dark", dark: false, storageThrows: true })).toBe("light");
  });
});
