"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Server, Database, Sun, Moon } from "lucide-react";

export function AppHeader() {
  const pathname = usePathname();
  const segment = pathname.split("/")[1] || "Overview";
  const title = segment.charAt(0).toUpperCase() + segment.slice(1).replace("-", " ");

  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    // Check saved theme or initial class on document
    const saved = localStorage.getItem("contextos-theme");
    const isDark = saved === "dark" || (!saved && document.documentElement.classList.contains("dark"));
    const currentTheme = isDark ? "dark" : "light";
    setTheme(currentTheme);
    document.documentElement.classList.toggle("dark", isDark);
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "light" ? "dark" : "light";
    setTheme(nextTheme);
    const isDark = nextTheme === "dark";
    document.documentElement.classList.toggle("dark", isDark);
    localStorage.setItem("contextos-theme", nextTheme);
    window.dispatchEvent(new CustomEvent("contextos-theme-change", { detail: { theme: nextTheme } }));
  };

  return (
    <header className="h-14 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-6 flex items-center justify-between transition-colors">
      <div className="flex items-center space-x-2 text-xs">
        <span className="text-slate-400 dark:text-slate-500">ContextOS</span>
        <span className="text-slate-300 dark:text-slate-600">/</span>
        <span className="font-semibold text-slate-800 dark:text-slate-100">{title}</span>
      </div>

      <div className="flex items-center space-x-3 text-xs">
        {/* PostgreSQL Database Status Pill */}
        <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 font-mono text-[11px]">
          <Database className="w-3.5 h-3.5 text-slate-400 dark:text-slate-500" />
          <span>PostgreSQL / pgvector</span>
        </div>

        {/* Backend API Status Pill */}
        <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 font-mono text-[11px]">
          <Server className="w-3.5 h-3.5 text-slate-400 dark:text-slate-500" />
          <span>API :8000</span>
        </div>

        {/* Global Dark / Bright Theme Switcher */}
        <button
          onClick={toggleTheme}
          className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-750 transition-colors text-xs font-medium shadow-xs"
          title={theme === "light" ? "Switch to Dark Mode" : "Switch to Bright Mode"}
        >
          {theme === "light" ? (
            <>
              <Sun className="w-3.5 h-3.5 text-amber-500" />
              <span className="text-[11px] font-mono">Bright</span>
            </>
          ) : (
            <>
              <Moon className="w-3.5 h-3.5 text-sky-400" />
              <span className="text-[11px] font-mono">Dark</span>
            </>
          )}
        </button>
      </div>
    </header>
  );
}
