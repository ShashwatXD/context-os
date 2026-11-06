"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Database,
  Layers,
  GitFork,
  Network,
  Bot,
  ShieldCheck,
  KeyRound,
  Activity,
  BarChart3,
} from "lucide-react";
import { cn } from "@/lib/utils/cn";

const NAV_ITEMS = [
  { name: "Overview", href: "/", icon: LayoutDashboard },
  { name: "Sources", href: "/sources", icon: Database },
  { name: "Catalog", href: "/catalog", icon: Layers },
  { name: "Lineage", href: "/lineage", icon: GitFork },
  { name: "Context Graph", href: "/graph", icon: Network },
  { name: "Context Agents", href: "/agents", icon: Bot },
  { name: "Governance", href: "/governance", icon: ShieldCheck },
  { name: "Agent Access (MCP)", href: "/agent-access", icon: KeyRound },
  { name: "Observability", href: "/observability", icon: Activity },
  { name: "Evaluations", href: "/evaluations", icon: BarChart3 },
];

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <aside className="w-64 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-screen select-none transition-colors">
      {/* Brand & Platform Identifier */}
      <div className="h-14 border-b border-slate-200 dark:border-slate-800 px-5 flex items-center justify-between">
        <div className="flex items-center space-x-2.5">
          <div className="w-6 h-6 rounded bg-slate-900 dark:bg-slate-100 flex items-center justify-center text-white dark:text-slate-900 font-bold text-xs tracking-wider">
            C
          </div>
          <div>
            <span className="font-semibold text-sm tracking-tight text-slate-900 dark:text-slate-100">ContextOS</span>
            <span className="text-[10px] ml-1.5 px-1.5 py-0.5 rounded font-mono bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
              v0.1
            </span>
          </div>
        </div>
      </div>

      {/* Navigation List */}
      <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
        <div className="px-3 py-1.5 text-[11px] font-semibold tracking-wider text-slate-400 dark:text-slate-500 uppercase">
          Console
        </div>
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center space-x-2.5 px-3 py-2 rounded text-xs font-medium transition-colors",
                isActive
                  ? "bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-white font-semibold"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-50 dark:hover:bg-slate-800/60"
              )}
            >
              <Icon className={cn("w-4 h-4", isActive ? "text-slate-900 dark:text-white" : "text-slate-400 dark:text-slate-500")} />
              <span>{item.name}</span>
            </Link>
          );
        })}
      </nav>

      {/* Footer System Status */}
      <div className="p-4 border-t border-slate-200 dark:border-slate-800 text-[11px] text-slate-500 dark:text-slate-400 flex items-center justify-between bg-slate-50 dark:bg-slate-850">
        <span className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span>Context Engine Active</span>
        </span>
        <span className="font-mono text-[10px] text-slate-400 dark:text-slate-500">MCP :8001</span>
      </div>
    </aside>
  );
}

