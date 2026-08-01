export default function Loading() {
  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center gap-8 px-6"
      style={{ backgroundColor: "var(--mf-stage)" }}
    >
      {/* Animated ring matching LoadingAnimation.js palette */}
      <div
        className="w-14 h-14 rounded-full animate-spin"
        style={{
          border: "3px solid var(--mf-line)",
          borderTopColor: "var(--mf-violet)",
          borderRightColor: "var(--mf-violet-soft)",
        }}
        aria-label="Yükleniyor"
      />

      {/* Skeleton cards */}
      <div className="w-full max-w-2xl space-y-3">
        {[100, 85, 70].map((w) => (
          <div
            key={w}
            className="glass rounded-2xl p-5 animate-pulse"
            style={{ border: "1px solid rgba(139,92,246,0.06)" }}
          >
            <div
              className="h-4 rounded mb-3"
              style={{ width: `${w}%`, backgroundColor: "var(--mf-panel-2)" }}
            />
            <div
              className="h-3 rounded mb-2"
              style={{ width: "65%", backgroundColor: "var(--mf-panel-2)" }}
            />
            <div
              className="h-3 rounded"
              style={{ width: "45%", backgroundColor: "var(--mf-panel-2)" }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
