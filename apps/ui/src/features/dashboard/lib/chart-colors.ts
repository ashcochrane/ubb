/**
 * Shared chart color constants for the dashboard feature.
 *
 * Recharts props need string literals, so these can't be pulled from the
 * Tailwind/CSS design tokens directly. When a color here changes, also update
 * the matching CSS var in `src/styles/app.css` to keep the two layers in sync.
 */

export const CHART_TERRACOTTA = "#a16a4a";
export const CHART_RED        = "#b84848";
export const CHART_GREEN      = "#3a8050";
export const CHART_STONE      = "#9a8e80";
export const CHART_MARGIN_DASH = "#b5ad9e";
