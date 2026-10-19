/** Pure helpers behind the animated numbers and the typed answer (tested without a browser). */

export function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - clamp01(t), 3);
}

/** Value `t` (0..1) of the way from `from` to `to`, easing out. */
export function interpolate(from: number, to: number, t: number): number {
  return from + (to - from) * easeOutCubic(t);
}

/** How many characters of a typed-out text are visible `elapsedMs` after it started. */
export function visibleCount(total: number, elapsedMs: number, msPerChar: number): number {
  if (total <= 0) return 0;
  if (msPerChar <= 0) return total;
  return Math.min(total, Math.max(0, Math.floor(elapsedMs / msPerChar)));
}

/** Milliseconds per character: slow enough to watch for short answers, never slower than 30 ms,
 * and never faster than 8 ms, so up to about 110 characters finish within a second. */
export function typingSpeed(totalChars: number): number {
  return Math.min(30, Math.max(8, 900 / Math.max(1, totalChars)));
}
