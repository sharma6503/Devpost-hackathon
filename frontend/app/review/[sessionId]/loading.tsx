export default function ReviewLoading() {
  return (
    <div className="h-screen flex flex-col bg-slate-50 overflow-hidden">
      {/* Header skeleton */}
      <div className="flex-shrink-0 flex items-center gap-4 px-6 py-3 border-b border-slate-200 bg-white shadow-sm">
        <div className="h-4 w-48 rounded skeleton" />
        <div className="ml-auto h-4 w-16 rounded skeleton" />
      </div>

      {/* Pipeline strip skeleton */}
      <div className="flex-shrink-0 border-b border-slate-200 bg-white px-6 py-6">
        <div className="flex items-center justify-center gap-8">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex flex-col items-center gap-2">
              <div className="w-12 h-12 rounded-full skeleton" />
              <div className="h-3 w-16 rounded skeleton" />
            </div>
          ))}
        </div>
      </div>

      {/* Main content skeleton */}
      <div className="flex flex-1 gap-6 px-6 py-5 overflow-hidden">
        <div className="flex-1 space-y-3">
          <div className="h-12 rounded-xl skeleton" />
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-24 rounded-xl skeleton" />
          ))}
        </div>
        <div className="w-96 flex-shrink-0">
          <div className="h-full rounded-xl" style={{ background: "var(--color-terminal-bg)", opacity: 0.3 }} />
        </div>
      </div>
    </div>
  );
}
