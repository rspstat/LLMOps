import { useEffect, useState } from "react";
import { formatPEasy } from "../format";
import AnimatedNumber from "./AnimatedNumber";

/** A bar that fills from empty to `value` (0..1) once it appears. */
export default function Gauge({ value }: { value: number }) {
  const [filled, setFilled] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setFilled(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  const percent = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <span className="gauge">
      <span className="gauge-track" aria-hidden="true">
        <span className="gauge-fill" style={{ width: filled ? `${percent}%` : "0%" }} />
      </span>
      <span className="gauge-value">
        <AnimatedNumber value={value} format={formatPEasy} durationMs={900} />
      </span>
    </span>
  );
}
