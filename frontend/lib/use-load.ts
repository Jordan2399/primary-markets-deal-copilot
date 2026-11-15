"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Load data when a component appears (and whenever `deps` change), with the three states every
 * screen needs: loading, error and data. `reload()` fetches again without clearing what is shown.
 *
 * A late answer from an older request is ignored, so quickly switching deals or filters can never
 * show the previous result on top of the new one.
 */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const latest = useRef(0); // number of the newest request

  const run = useCallback(() => {
    const mine = ++latest.current;
    setLoading(true);
    load()
      .then((value) => {
        if (mine !== latest.current) return; // a newer request has started: drop this answer
        setData(value);
        setError(null);
      })
      .catch((e) => {
        if (mine === latest.current) setError(e);
      })
      .finally(() => {
        if (mine === latest.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    run();
  }, [run]);

  return { data, error, loading, reload: run };
}
