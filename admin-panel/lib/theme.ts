const STORAGE_KEY = "movie_platform_theme";

export type Theme = "dark" | "light";

// Inlined as a string (not imported) into a <script> tag in app/layout.tsx so
// it runs before React hydrates/paints — reading localStorage and applying
// the class in a useEffect would flash light mode for a frame on every load.
// Defaults to dark (not the system preference) since a plain, unrequested
// light default is exactly what looked "juda yorqin" (too bright) before.
export const THEME_INIT_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem('${STORAGE_KEY}');
    var theme = stored === 'light' ? 'light' : 'dark';
    document.documentElement.classList.toggle('dark', theme === 'dark');
  } catch (e) {}
})();
`;

export function getTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  return localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
}

export function setTheme(theme: Theme): void {
  localStorage.setItem(STORAGE_KEY, theme);
  document.documentElement.classList.toggle("dark", theme === "dark");
}
