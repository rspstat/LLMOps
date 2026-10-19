import { useCountUp } from "../hooks/useCountUp";

interface Props {
  value: number;
  /** Turns the animated number into the text shown. */
  format?: (value: number) => string;
  durationMs?: number;
}

/** Counts up to `value` (and from the previous value when it changes). */
export default function AnimatedNumber({ value, format = (v) => String(Math.round(v)), durationMs }: Props) {
  const shown = useCountUp(value, durationMs);
  return (
    <>
      <span aria-hidden="true">{format(shown)}</span>
      <span className="sr-only">{format(value)}</span>
    </>
  );
}
