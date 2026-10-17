// An institution's colours (set by platform staff in the Django admin) override
// the role palettes in index.css: the server sends ready-made CSS variables
// (`institution.theme.palette`, see server/institutions/theme.py), set here on
// <html> so every primary, secondary, accent-* and accent2-* colour follows them.
// The chosen colours arrive as `--color-primary` / `--color-secondary` and are used
// as-is for solid fills; hover shades are derived from them in index.css.

const NAME = /^--color-((on-)?(primary|secondary)|accent2?-\d{2,3})$/;
const VALUE = /^#[0-9a-f]{6}$/i;
let applied = [];

/** Use `palette` ({ "--color-primary": "#2563eb", ... }), or the default theme when null. */
export const applyTheme = (palette) => {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  applied.forEach((name) => root.style.removeProperty(name));
  applied = [];
  for (const [name, value] of Object.entries(palette ?? {})) {
    if (!NAME.test(name) || !VALUE.test(value)) continue;
    root.style.setProperty(name, value);
    applied.push(name);
  }
  if (applied.length) root.dataset.theme = "institution";
  else delete root.dataset.theme;
};
