/**
 * Share one in-flight promise across concurrent callers so simultaneous
 * failures trigger a single refresh instead of a storm. The slot resets
 * after the call settles, so a later failure refreshes again.
 */
export function createSingleflight<T>(fn: () => Promise<T>): () => Promise<T> {
  let inflight: Promise<T> | null = null;
  return () => {
    if (inflight === null) {
      inflight = Promise.resolve().then(fn);
      inflight.then(
        () => {
          inflight = null;
        },
        () => {
          inflight = null;
        },
      );
    }
    return inflight;
  };
}
