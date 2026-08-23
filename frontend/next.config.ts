import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";

// Pragmatic, no-nonce Content-Security-Policy. Notes on the loosened directives:
//  - style-src 'unsafe-inline': framer-motion sets inline `style` attributes and
//    Next/Tailwind inject <style> blocks. A strict nonce CSP would force dynamic
//    rendering of every route — deliberately deferred.
//  - script-src 'unsafe-eval' only in dev (React Refresh / Next dev tooling).
//  - img-src data:/blob: — the metrics chart is a base64 data URI and artifacts
//    are previewed via object URLs.
//  - frame-src blob: — the HTML audit report is opened from a blob URL.
//  - connect-src 'self' — the app talks to the backend through the same-origin
//    /api/adk proxy (including the run_sse stream), so 'self' is sufficient.
//  - The generated HTML audit report (report.html) is now fully self-contained:
//    Tailwind CSS, Chart.js and the (subsetted) Material Symbols icon font are
//    all inlined by html_agent.py — no external CDNs. It renders in a blob: tab /
//    srcdoc iframe that INHERITS this policy; the inlined <style>/<script> are
//    covered by 'unsafe-inline', and the base64 @font-face needs font-src data:.

const csp = [
  "default-src 'self'",
  "img-src 'self' data: blob:",
  "style-src 'self' 'unsafe-inline'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "font-src 'self' data:",
  "object-src 'none'",
  "base-uri 'self'",
  "frame-ancestors 'self'",
  "frame-src 'self' blob:",
  "connect-src 'self'",
].join("; ");

const securityHeaders = [
  // Kept SAMEORIGIN (not DENY): the report can be framed same-origin.
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Content-Security-Policy", value: csp },
];

const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
