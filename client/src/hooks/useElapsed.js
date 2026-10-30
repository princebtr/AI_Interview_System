import { useEffect, useState } from "react";

/** Milliseconds since `start` (a timestamp), ticking every second; 0 without a start. */
export const useElapsed = (start) => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!start) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [start]);
  return start ? Math.max(0, now - start) : 0;
};
