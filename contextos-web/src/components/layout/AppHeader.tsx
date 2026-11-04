"use client";

import { usePathname } from "next/navigation";
import { Server, Database } from "lucide-react";

export function AppHeader() {
  const pathname = usePathname();
  const segment = pathname.split("/")[1] || "Overview";
  const title = segment.charAt(0).toUpperCase() + segment.slice(1).replace("-", " ");

  return (
    <header className="h-14 border-b border-slate-200 bg-white px-6 flex items-center justify-between">
      <div className="flex items-center space-x-2 text-xs">
        <span className="text-slate-400">ContextOS</span>
        <span className="text-slate-300">/</span>
        <span className="font-semibold text-slate-800">{title}</span>
      </div>

      <div className="flex items-center space-x-3 text-xs">
        <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded bg-slate-50 border border-slate-200 text-slate-600 font-mono text-[11px]">
          <Database className="w-3.5 h-3.5 text-slate-400" />
          <span>PostgreSQL / pgvector</span>
        </div>

        <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded bg-slate-50 border border-slate-200 text-slate-600 font-mono text-[11px]">
          <Server className="w-3.5 h-3.5 text-slate-400" />
          <span>API :8000</span>
        </div>
      </div>
    </header>
  );
}

