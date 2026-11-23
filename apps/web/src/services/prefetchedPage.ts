const ttlMs = 30_000;

export function createPrefetchedPage<T>() {
  let entry: { key: string; promise: Promise<T>; expiresAt: number } | undefined;

  return {
    load(queryKey: readonly unknown[], fetchPage: () => Promise<T>): Promise<T> {
      const key = JSON.stringify(queryKey);
      if (entry?.key === key && entry.expiresAt > Date.now()) return entry.promise;

      const next = { key, promise: fetchPage(), expiresAt: Infinity };
      entry = next;
      void next.promise.then(
        () => { next.expiresAt = Date.now() + ttlMs; },
        () => { if (entry === next) entry = undefined; },
      );
      return next.promise;
    },
    clear() { entry = undefined; },
  };
}
