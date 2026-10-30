import { useEffect, useState } from "react";

/**
 * Current time on the server's clock, ticking every second. Pass the
 * `serverTime` from an API response so countdowns don't depend on whether the
 * student's computer clock is right.
 *
 * The offset is adopted during the render that receives a new `serverTime`
 * (not in an effect), so no committed render or effect ever sees the device
 * clock: a fast clock can't make a test look closed and auto-submit it early.
 */
export const useServerClock = (serverTime) => {
  const [sync, setSync] = useState({ serverTime: null, offset: 0 });
  if (serverTime && serverTime !== sync.serverTime) {
    setSync({ serverTime, offset: new Date(serverTime).getTime() - Date.now() });
  }

  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  return Date.now() + sync.offset;
};
