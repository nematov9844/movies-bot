"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

import { getTheme, setTheme, type Theme } from "@/lib/theme";

export function ThemeToggle() {
  const [theme, setThemeState] = useState<Theme | null>(null);

  useEffect(() => {
    setThemeState(getTheme());
  }, []);

  function toggle() {
    const next: Theme = theme === "light" ? "dark" : "light";
    setTheme(next);
    setThemeState(next);
  }

  if (theme === null) return <div className="h-9 w-9" />; // avoid a layout jump before mount

  return (
    <button
      onClick={toggle}
      className="flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      title={theme === "dark" ? "Yorug' rejim" : "Qorong'i rejim"}
      aria-label="Mavzuni almashtirish"
    >
      {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}
