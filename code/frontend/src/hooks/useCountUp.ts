import { useEffect, useRef, useState } from "react";
import { clamp01, interpolate } from "../motion";
import { useReducedMotion } from "./useReducedMotion";

/** Animates from the value currently shown to `target`. Starts at 0 on first render. */
export function useCountUp(target: number, durationMs = 800): number {
  const reduced = useReducedMotion();
  const [value, setValue] = useState(reduced ? target : 0);
  const shown = useRef(value);

  useEffect(() => {
    if (reduced) {
      shown.current = target;
      setValue(target);
      return;
    }
    const from = shown.current;
    if (from === target) return;
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = clamp01((now - start) / durationMs);
      const current = t >= 1 ? target : interpolate(from, target, t);
      shown.current = current;
      setValue(current);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, durationMs, reduced]);

  return value;
}
