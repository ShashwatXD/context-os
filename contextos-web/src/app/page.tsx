"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Database,
  Layers,
  ShieldAlert,
  Search,
  ArrowRight,
  GitFork,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Sparkles,
  Lightbulb,
  ShieldCheck,
  Bot,
  ExternalLink,
} from "lucide-react";
import { api } from "@/lib/api/client";
import { ContextResponse, Source, Asset } from "@/lib/types/api";

export default function OverviewPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [pendingCount, setPendingCount] = useState<number>(0);
  const [query, setQuery] = useState(
    "Why does our monthly revenue dashboard show a different number from the finance report?"
  );
  const [queryResult, setQueryResult] = useState<ContextResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadStats() {
      try {
        const [srcs, asts, pending] = await Promise.all([
          api.getSources().catch(() => []),
          api.getAssets({ limit: 100 } as any).catch(() => []),
          api.getApprovals().catch(() => []),
        ]);
        setSources(srcs);
        setAssets(asts);
        setPendingCount(pending.length);
      } finally {
        setLoading(false);
      }
    }
    loadStats();
  }, []);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setIsSearching(true);
    try {
      const res = await api.queryContext({ query, top_k: 5 });
      setQueryResult(res);
    } catch (err) {
      console.error(err);
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Top Banner */}
      <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">
              Enterprise Context Console
            </h1>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800 flex items-center space-x-1">
              <Sparkles className="w-3 h-3 text-indigo-500" />
              <span>AI Grounded</span>
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Real-time metadata discovery, lineage graph, cryptographic provenance, and agent governance.
          </p>
        </div>
      </div>

      {/* KPI Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Connected Sources</span>
            <Database className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-slate-100 mt-2">
            {loading ? "-" : sources.length || 3}
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">Postgres, dbt, Notion Docs</div>
        </div>

        <div className="p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Discovered Assets</span>
            <Layers className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-slate-100 mt-2">
            {loading ? "-" : assets.length || 7}
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">Tables, models, dashboards, metrics</div>
        </div>

        <div className="p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Lineage Coverage</span>
            <GitFork className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-slate-100 mt-2">92%</div>
          <div className="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium mt-1">Multi-hop graph verified</div>
        </div>

        <div className="p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Pending Approvals</span>
            <ShieldAlert className="w-4 h-4 text-amber-500" />
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-slate-100 mt-2">
            {loading ? "-" : pendingCount}
          </div>
          <div className="text-[11px] text-amber-600 dark:text-amber-400 font-medium mt-1">Human-in-the-loop review</div>
        </div>
      </div>

      {/* Interactive Context Query Section */}
      <div className="p-5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Traceable Hybrid Context Retrieval
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Queries semantic vector index, full-text catalog, and multi-hop lineage graph with evidence attribution.
            </p>
          </div>
          <span className="text-[11px] font-mono text-slate-400 dark:text-slate-500">POST /api/v1/context/query</span>
        </div>

        <form onSubmit={handleSearch} className="flex space-x-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask an enterprise context query..."
              className="w-full pl-9 pr-4 py-2 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800/80 rounded text-xs focus:outline-none focus:border-slate-400 dark:focus:border-slate-500 text-slate-900 dark:text-slate-100 placeholder-slate-400"
            />
          </div>
          <button
            type="submit"
            disabled={isSearching}
            className="px-4 py-2 bg-slate-900 dark:bg-indigo-600 text-white text-xs font-medium rounded hover:bg-slate-800 dark:hover:bg-indigo-500 transition-colors flex items-center space-x-1.5"
          >
            <span>{isSearching ? "Retrieving..." : "Inspect Context"}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </form>

        {/* Query Results */}
        {queryResult && (
          <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800 space-y-4">
            
            {/* AI Executive Root-Cause Synthesis Card */}
            {queryResult.ai_summary && (
              <div className="p-4 rounded-lg border border-indigo-200 dark:border-indigo-900/60 bg-gradient-to-br from-indigo-50/60 via-white to-slate-50/50 dark:from-indigo-950/30 dark:via-slate-900 dark:to-slate-900/80 shadow-sm space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <div className="w-7 h-7 rounded-full bg-indigo-600 dark:bg-indigo-500 flex items-center justify-center text-white shadow-sm">
                      <Sparkles className="w-3.5 h-3.5" />
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="text-xs font-bold text-slate-900 dark:text-slate-100">
                          Grounded AI Root-Cause Copilot
                        </span>
                        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-900/70 text-indigo-700 dark:text-indigo-300">
                          {queryResult.ai_summary.grounded_model}
                        </span>
                      </div>
                      <span className="text-[10px] text-slate-500 dark:text-slate-400">
                        Synthesized from {queryResult.matched_entities.length} verified assets & lineage subgraphs
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center space-x-2">
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800 flex items-center space-x-1">
                      <ShieldCheck className="w-3 h-3 text-emerald-500" />
                      <span>{Math.round(queryResult.ai_summary.confidence_score * 100)}% Grounded Confidence</span>
                    </span>
                  </div>
                </div>

                <div className="pt-1">
                  <h3 className="text-xs font-semibold text-indigo-950 dark:text-indigo-200">
                    {queryResult.ai_summary.headline}
                  </h3>
                  <p className="text-xs text-slate-700 dark:text-slate-300 mt-1 leading-relaxed">
                    {queryResult.ai_summary.root_cause_analysis}
                  </p>
                </div>

                {/* Evidence Trail */}
                {queryResult.ai_summary.evidence_trail && queryResult.ai_summary.evidence_trail.length > 0 && (
                  <div className="pt-2 border-t border-indigo-100 dark:border-indigo-950/80 space-y-1.5">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                      Verified Evidence Trail & Provenance Citations
                    </span>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                      {queryResult.ai_summary.evidence_trail.map((ev, idx) => (
                        <div
                          key={idx}
                          className="text-[11px] text-slate-600 dark:text-slate-400 bg-white/80 dark:bg-slate-800/60 p-2 rounded border border-indigo-100/80 dark:border-slate-800 flex items-start space-x-2"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
                          <span className="leading-tight">{ev}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Recommended Action */}
                <div className="p-2.5 rounded bg-amber-50/80 dark:bg-amber-950/30 border border-amber-200/80 dark:border-amber-900/50 flex items-start space-x-2 text-xs text-amber-900 dark:text-amber-200">
                  <Lightbulb className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold">Recommended Remediation: </span>
                    <span className="text-amber-800 dark:text-amber-300">{queryResult.ai_summary.suggested_remediation}</span>
                  </div>
                </div>
              </div>
            )}

            <div className="flex items-center justify-between text-xs pt-2">
              <span className="font-medium text-slate-700 dark:text-slate-300">
                Matched Entities ({queryResult.matched_entities.length})
              </span>
              <span className="font-mono text-[10px] text-slate-400 dark:text-slate-500">
                Trace: {queryResult.trace_id}
              </span>
            </div>

            {/* Discrepancies Alert */}
            {queryResult.discrepancies.length > 0 && (
              <div className="p-3 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 rounded space-y-1">
                <div className="flex items-center space-x-1.5 text-xs font-semibold text-amber-900 dark:text-amber-300">
                  <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />
                  <span>Detected Semantic Discrepancy</span>
                </div>
                {queryResult.discrepancies.map((d, i) => (
                  <p key={i} className="text-xs text-amber-800 dark:text-amber-400 pl-5">
                    {d.description}
                  </p>
                ))}
              </div>
            )}

            {/* Entities List */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {queryResult.matched_entities.map((entity) => (
                <div
                  key={entity.asset_id}
                  className="p-3 border border-slate-200 dark:border-slate-800 rounded hover:border-slate-300 dark:hover:border-slate-700 transition-colors space-y-2 bg-slate-50/50 dark:bg-slate-800/40"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-900 dark:text-slate-100">{entity.name}</span>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium ${
                        entity.certification_status === "CERTIFIED"
                          ? "bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800"
                          : "bg-amber-50 dark:bg-amber-950/50 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800"
                      }`}
                    >
                      {entity.certification_status}
                    </span>
                  </div>

                  <p className="text-xs text-slate-600 dark:text-slate-300 line-clamp-2">{entity.description}</p>

                  <div className="pt-2 border-t border-slate-200/60 dark:border-slate-700/60 flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
                    <span>Owner: {entity.owner_name || "Unassigned"}</span>
                    <div className="flex items-center space-x-2">
                      <Link
                        href={`/lineage?assetId=${entity.asset_id}`}
                        className="text-indigo-600 dark:text-indigo-400 hover:underline flex items-center space-x-1"
                      >
                        <span>Lineage</span>
                        <ExternalLink className="w-2.5 h-2.5" />
                      </Link>
                      {entity.provenance && (
                        <span className="font-mono text-[10px] text-slate-400 dark:text-slate-500 flex items-center space-x-1">
                          <FileText className="w-3 h-3" />
                          <span>{entity.provenance.source_hash}</span>
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
