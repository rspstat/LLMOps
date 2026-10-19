// Runs before the first paint (loaded from <head>) so the page never flashes the wrong theme.
// Mirrors resolveTheme() in src/theme.ts; src/theme.test.ts runs this file to keep them in sync.
(function () {
  var stored = null;
  try {
    stored = window.localStorage.getItem("llmops-demo-theme");
  } catch (e) {
    // storage can be blocked (private windows, site data off): fall back to the system setting
  }
  var dark = false;
  try {
    dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch (e) {
    // no matchMedia: stay light
  }
  var theme = stored === "light" || stored === "dark" ? stored : dark ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", theme);
})();
