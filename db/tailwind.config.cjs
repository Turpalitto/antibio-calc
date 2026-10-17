// Audit 2026-10-14 (H-1): static Tailwind build replacing the Play-CDN runtime
// compiler (vendor/tailwind.js, 407 KB of JS parsed on every launch, CSS
// generated in the browser). Same Tailwind line as the CDN bundle (3.4.17) and
// the same configuration it was given inline (`darkMode: 'class'`).
//
// `content` is the single-file shell template: Tailwind's extractor scans the
// WHOLE file (markup and JS strings alike), so classes assembled in JS from
// complete literals are picked up. Classes glued together from fragments
// (`'text-' + colour`) would not be — the template does not do that, and
// clinical_engine/tests/test_tailwind_static_css.py checks every class token
// in the template and in the rendered shell against the generated CSS.
//
// Regenerate: `npm run build:css` (writes vendor/app.css, committed).
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./antibiotic_calc.html.template"],
  darkMode: "class",
  theme: { extend: {} },
  plugins: [],
};
