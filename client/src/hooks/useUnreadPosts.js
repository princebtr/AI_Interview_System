import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import api from "../utils/axios";
import { READ_EVENT } from "../utils/board";

const REFRESH_MS = 2 * 60 * 1000;

/** How many notes and messages the student hasn't opened (always 0 when `enabled` is false). */
export const useUnreadPosts = (enabled) => {
  const [count, setCount] = useState(0);
  const { pathname } = useLocation();

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    const load = () =>
      api
        .get("/board/unread")
        .then(({ data }) => !cancelled && setCount(data.unread))
        .catch(() => {}); // a badge isn't worth an error toast
    load();
    const timer = setInterval(load, REFRESH_MS);
    window.addEventListener(READ_EVENT, load);
    return () => {
      cancelled = true;
      clearInterval(timer);
      window.removeEventListener(READ_EVENT, load);
    };
  }, [enabled, pathname]);

  return enabled ? count : 0;
};
