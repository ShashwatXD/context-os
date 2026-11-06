import type { Metadata } from "next";
import "./globals.css";
import { SidebarNav } from "@/components/layout/SidebarNav";
import { AppHeader } from "@/components/layout/AppHeader";

export const metadata: Metadata = {
  title: "ContextOS — Enterprise Context Infrastructure Platform",
  description: "Verifiable enterprise context infrastructure for AI agents",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 flex transition-colors">
        <SidebarNav />
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <AppHeader />
          <main className="flex-1 overflow-y-auto p-6 bg-slate-50 dark:bg-slate-950 transition-colors">{children}</main>
        </div>
      </body>
    </html>
  );
}

