import { useEffect, useState } from "react";
import { typingSpeed, visibleCount } from "../motion";
import { useReducedMotion } from "./useReducedMotion";

/** The first part of `text`, growing like typing; the whole text at once if motion is reduced. */
export function useTypewriter(text: string): { shown: string; done: boolean } {
  const reduced = useReducedMotion();
  const chars = Array.from(text); // code points, so Korean and emoji are never cut in half
  const [count, setCount] = useState(reduced ? chars.length : 0);

  useEffect(() => {
    const total = Array.from(text).length;
    if (reduced) {
      setCount(total);
      return;
    }
    setCount(0);
    const msPerChar = typingSpeed(total);
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const next = visibleCount(total, now - start, msPerChar);
      setCount(next);
      if (next < total) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [text, reduced]);

  return { shown: chars.slice(0, count).join(""), done: count >= chars.length };
}
