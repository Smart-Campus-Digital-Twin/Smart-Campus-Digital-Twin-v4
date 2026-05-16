import { useState, useEffect, useRef } from "react";

export function useAnimatedValue(target: number, decimals = 0, duration = 600): number {
  const [display, setDisplay] = useState(target);
  const prev = useRef(target);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const start = prev.current;
    const end = target;
    if (start === end) return;

    const startTime = performance.now();

    const tick = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = start + (end - start) * eased;
      setDisplay(parseFloat(current.toFixed(decimals)));

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        prev.current = end;
      }
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, decimals, duration]);

  return display;
}