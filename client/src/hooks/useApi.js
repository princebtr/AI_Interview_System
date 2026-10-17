import { useCallback, useEffect, useState } from "react";
import api from "../utils/axios";

/**
 * GET `url` (with optional query `params`) and track loading/error state.
 * Re-fetches when url/params change; `reload()` fetches again and keeps the
 * previous data on screen meanwhile. Stale responses are ignored.
 */
export const useApi = (url, params) => {
  const key = JSON.stringify([url, params ?? null]);
  const [state, setState] = useState({ data: null, loading: Boolean(url), error: null });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!url) return undefined;
    let cancelled = false;
    setState((prev) => ({ ...prev, loading: true, error: null }));
    api.get(url, { params }).then(
      ({ data }) => !cancelled && setState({ data, loading: false, error: null }),
      (error) => !cancelled && setState((prev) => ({ ...prev, loading: false, error }))
    );
    return () => {
      cancelled = true;
    };
    // `key` captures url + params by value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, reload };
};
