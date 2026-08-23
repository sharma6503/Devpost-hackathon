import { motion } from "framer-motion";
import { ShieldOff, Home, Search } from "lucide-react";
import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
      <div className="max-w-md w-full text-center space-y-6">
        <div className="flex justify-center">
          <div className="w-20 h-20 rounded-2xl bg-slate-100 border border-slate-200 flex items-center justify-center">
            <ShieldOff className="w-10 h-10 text-slate-400" />
          </div>
        </div>

        <div>
          <p className="text-sm font-mono text-slate-400 mb-2">404</p>
          <h1 className="text-2xl font-bold text-slate-900">Page not found</h1>
          <p className="mt-2 text-sm text-slate-500">
            This page doesn&apos;t exist, or the session may have expired.
          </p>
        </div>

        <div className="flex items-center justify-center gap-3">
          <Link
            href="/"
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium shadow-sm transition-colors"
          >
            <Home className="w-3.5 h-3.5" />
            Start new audit
          </Link>
        </div>
      </div>
    </div>
  );
}
