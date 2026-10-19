import { describe, expect, it } from "vitest";
import { clamp01, easeOutCubic, interpolate, typingSpeed, visibleCount } from "./motion";

describe("easing and interpolation", () => {
  it("starts at the start, ends at the end and never overshoots", () => {
    expect(interpolate(10, 50, 0)).toBe(10);
    expect(interpolate(10, 50, 1)).toBe(50);
    for (let t = 0; t <= 1.0001; t += 0.05) {
      const value = interpolate(10, 50, t);
      expect(value).toBeGreaterThanOrEqual(10);
      expect(value).toBeLessThanOrEqual(50);
    }
  });

  it("eases out: most of the distance is covered early", () => {
    expect(easeOutCubic(0.5)).toBeGreaterThan(0.5);
    expect(easeOutCubic(0.5)).toBeCloseTo(0.875);
  });

  it("clamps time outside 0..1 and works downwards", () => {
    expect(clamp01(-3)).toBe(0);
    expect(clamp01(9)).toBe(1);
    expect(interpolate(5, 1, 2)).toBe(1);
    expect(interpolate(5, 1, -1)).toBe(5);
  });
});

describe("typing", () => {
  it("reveals characters over time and stops at the full length", () => {
    expect(visibleCount(10, 0, 20)).toBe(0);
    expect(visibleCount(10, 59, 20)).toBe(2);
    expect(visibleCount(10, 60, 20)).toBe(3);
    expect(visibleCount(10, 10_000, 20)).toBe(10);
  });

  it("handles empty text, a zero speed and a clock that ran backwards", () => {
    expect(visibleCount(0, 500, 20)).toBe(0);
    expect(visibleCount(7, 5, 0)).toBe(7);
    expect(visibleCount(7, -50, 20)).toBe(0);
  });

  it("types short answers slowly and long ones within about a second", () => {
    expect(typingSpeed(5)).toBe(30);
    expect(typingSpeed(1000)).toBe(8);
    const total = 120;
    expect(typingSpeed(total) * total).toBeLessThanOrEqual(1000);
    expect(typingSpeed(0)).toBeGreaterThan(0);
  });
});
