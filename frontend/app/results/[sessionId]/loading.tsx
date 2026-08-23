export default function ResultsLoading() {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      {/* Header skeleton */}
      <div className="border-b border-slate-200 bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center gap-4">
          <div className="w-8 h-8 rounded-lg skeleton" />
          <div className="w-20 h-20 rounded-2xl skeleton" />
          <div className="space-y-2">
            <div className="h-5 w-32 rounded skeleton" />
            <div className="h-3 w-48 rounded skeleton" />
          </div>
        </div>
        {/* Tab bar skeleton */}
        <div className="max-w-7xl mx-auto px-6 flex gap-1 border-t border-slate-100 py-1">
          {Array.from({ length: 7 }).map((_, i) => (
            <div key={i} className="h-8 w-20 rounded-lg skeleton mx-1" />
          ))}
        </div>
      </div>

      {/* Content skeleton */}
      <div className="max-w-7xl w-full mx-auto px-6 py-8 space-y-4">
        {/* Score bars */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="p-4 rounded-xl border border-slate-200 bg-white shadow-sm space-y-3">
              <div className="flex justify-between">
                <div className="h-4 w-24 rounded skeleton" />
                <div className="h-4 w-12 rounded skeleton" />
              </div>
              <div className="h-2 rounded-full skeleton" />
            </div>
          ))}
        </div>
        {/* Severity cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 rounded-xl skeleton" />
          ))}
        </div>
        {/* Summary panel */}
        <div className="h-48 rounded-xl skeleton" />
      </div>
    </div>
  );
}
