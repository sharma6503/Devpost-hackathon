"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";
import { FileX, RefreshCw, Home } from "lucide-react";
import Link from "next/link";

export default function ResultsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[ResultsError]", error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 200, damping: 20 }}
        className="max-w-md w-full text-center space-y-5"
      >
        <div className="flex justify-center">
          <div className="w-16 h-16 rounded-2xl bg-slate-100 border border-slate-200 flex items-center justify-center">
            <FileX className="w-8 h-8 text-slate-500" />
          </div>
        </div>
        <div>
          <h1 className="text-xl font-bold text-slate-900">Couldn&apos;t load results</h1>
          <p className="mt-1.5 text-sm text-slate-500">
            The audit results could not be retrieved. The session may have expired or the ADK backend is offline.
          </p>
        </div>
        <div className="flex justify-center gap-3">
          <button
            onClick={reset}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Retry
          </button>
          <Link href="/" className="flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 text-sm font-medium transition-colors">
            <Home className="w-3.5 h-3.5" />
            New audit
          </Link>
        </div>
      </motion.div>
    </div>
  );
}
