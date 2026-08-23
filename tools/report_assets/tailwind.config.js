/**
 * Tailwind v3 config for the OFFLINE build of the HTML audit report stylesheet.
 *
 * This MUST mirror the `tailwind.config` block that used to live inline in
 * report_template.html (loaded via the Tailwind Play CDN). The CDN was removed so
 * the report is fully self-contained; this config + `npm run build` reproduces the
 * exact same utility CSS, compiled to agent_guardian/templates/vendor/report.css.
 *
 * `content` scans BOTH the template and the Python modules that emit utility
 * classes into the report at runtime (findings/governance/expert-review cards),
 * so JIT never purges a class that only appears in generated fragments.
 */
module.exports = {
  content: [
    "../../agent_guardian/templates/**/*.html",
    "../../agent_guardian/**/*.py",
  ],
  theme: {
    extend: {
      colors: {
        on: {
          primary: {
            fixed: "#ffffff",
          },
        },
        primary: {
          DEFAULT: "#0054a6",
          container: "#0054a6",
          dim: "#003b75",
        },
        surface: {
          DEFAULT: "#f8fafc",
          dim: "#f8fafc",
          container: {
            lowest: "#ffffff",
            low: "#f8fafc",
            DEFAULT: "#f1f5f9",
            high: "#e2e8f0",
            highest: "#cbd5e1",
          },
        },
        tertiary: {
          DEFAULT: "#16a34a",
          container: "#15803d",
        },
        error: {
          DEFAULT: "#dc2626",
          container: "#991b1b",
        },
        outline: {
          DEFAULT: "#94a3b8",
          variant: "#e2e8f0",
        },
      },
      fontFamily: {
        headline: ["system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
        body: ["system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
        label: ["system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
      },
    },
  },
  plugins: [
    require("@tailwindcss/forms"),
    require("@tailwindcss/typography"),
    require("@tailwindcss/container-queries"),
  ],
};
