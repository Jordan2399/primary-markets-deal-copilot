/**
 * Grey placeholder blocks shown while data loads. They keep the page from jumping when the real
 * content arrives, and read better than the word "Loading...". The shimmer is switched off for
 * people who ask their system for reduced motion (see the CSS).
 */
export function Skeleton({ lines = 3, height = 14 }: { lines?: number; height?: number }) {
  return (
    <div className="skeleton-group" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        // The last line is shorter, like the end of a paragraph.
        <div key={i} className="skeleton" style={{ height, width: i === lines - 1 && lines > 1 ? "60%" : "100%" }} />
      ))}
    </div>
  );
}

/** A card-shaped placeholder: a title bar and a few lines. `label` is read aloud once to screen readers. */
export function CardSkeleton({ lines = 4, label = "Loading" }: { lines?: number; label?: string }) {
  return (
    <section className="card" role="status" aria-label={label}>
      <div className="skeleton" style={{ height: 18, width: "30%", marginBottom: 14 }} aria-hidden="true" />
      <Skeleton lines={lines} />
    </section>
  );
}
