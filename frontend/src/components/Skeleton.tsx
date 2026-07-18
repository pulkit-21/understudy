/** Shimmering placeholder rows shown while a list loads — premium perceived
 *  performance instead of a bare "Loading…" spinner. */
export function SkeletonList({ rows = 4, widths }: { rows?: number; widths?: string[] }) {
  const w = widths ?? ["70%", "55%", "62%", "48%", "66%", "52%"];
  return (
    <div className="card" style={{ padding: 18 }} aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading…</span>
      {Array.from({ length: rows }).map((_, i) => (
        <div className="skel-line" key={i}>
          <div className="skeleton" style={{ width: 26, height: 26, borderRadius: 7, flex: "none" }} />
          <div className="skeleton skeleton-row" style={{ width: w[i % w.length], height: 16 }} />
        </div>
      ))}
    </div>
  );
}
