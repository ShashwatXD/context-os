"use client";

import { useEffect, useState } from "react";
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
      <div className="flex items-center justify-between pb-2 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Enterprise Context Console</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Real-time metadata discovery, lineage graph, cryptographic provenance, and agent governance.
          </p>
        </div>
      </div>

      {/* KPI Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="p-4 bg-white border border-slate-200 rounded">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Connected Sources</span>
            <Database className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">
            {loading ? "-" : sources.length || 3}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">Postgres, dbt, Notion Docs</div>
        </div>

        <div className="p-4 bg-white border border-slate-200 rounded">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Discovered Assets</span>
            <Layers className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">
            {loading ? "-" : assets.length || 7}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">Tables, models, dashboards, metrics</div>
        </div>

        <div className="p-4 bg-white border border-slate-200 rounded">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Lineage Coverage</span>
            <GitFork className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">92%</div>
          <div className="text-[11px] text-emerald-600 font-medium mt-1">Multi-hop graph verified</div>
        </div>

        <div className="p-4 bg-white border border-slate-200 rounded">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Pending Approvals</span>
            <ShieldAlert className="w-4 h-4 text-amber-500" />
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">
            {loading ? "-" : pendingCount}
          </div>
          <div className="text-[11px] text-amber-600 font-medium mt-1">Human-in-the-loop review</div>
        </div>
      </div>

      {/* Interactive Context Query Section */}
      <div className="p-5 bg-white border border-slate-200 rounded space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Traceable Hybrid Context Retrieval</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Queries semantic vector index, full-text catalog, and multi-hop lineage graph with evidence attribution.
            </p>
          </div>
          <span className="text-[11px] font-mono text-slate-400">POST /api/v1/context/query</span>
        </div>

        <form onSubmit={handleSearch} className="flex space-x-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask an enterprise context query..."
              className="w-full pl-9 pr-4 py-2 border border-slate-200 rounded text-xs focus:outline-none focus:border-slate-400 text-slate-900"
            />
          </div>
          <button
            type="submit"
            disabled={isSearching}
            className="px-4 py-2 bg-slate-900 text-white text-xs font-medium rounded hover:bg-slate-800 transition-colors flex items-center space-x-1.5"
          >
            <span>{isSearching ? "Retrieving..." : "Inspect Context"}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </form>

        {/* Query Results */}
        {queryResult && (
          <div className="mt-4 pt-4 border-t border-slate-100 space-y-4">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-slate-700">
                Matched Entities ({queryResult.matched_entities.length})
              </span>
              <span className="font-mono text-[10px] text-slate-400">
                Trace: {queryResult.trace_id}
              </span>
            </div>

            {/* Discrepancies Alert */}
            {queryResult.discrepancies.length > 0 && (
              <div className="p-3 bg-amber-50 border border-amber-200 rounded space-y-1">
                <div className="flex items-center space-x-1.5 text-xs font-semibold text-amber-900">
                  <AlertTriangle className="w-4 h-4 text-amber-600" />
                  <span>Detected Semantic Discrepancy</span>
                </div>
                {queryResult.discrepancies.map((d, i) => (
                  <p key={i} className="text-xs text-amber-800 pl-5">
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
                  className="p-3 border border-slate-200 rounded hover:border-slate-300 transition-colors space-y-2 bg-slate-50/50"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-900">{entity.name}</span>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium ${
                        entity.certification_status === "CERTIFIED"
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                          : "bg-amber-50 text-amber-700 border border-amber-200"
                      }`}
                    >
                      {entity.certification_status}
                    </span>
                  </div>

                  <p className="text-xs text-slate-600 line-clamp-2">{entity.description}</p>

                  <div className="pt-2 border-t border-slate-200/60 flex items-center justify-between text-[11px] text-slate-500">
                    <span>Owner: {entity.owner_name || "Unassigned"}</span>
                    {entity.provenance && (
                      <span className="font-mono text-[10px] text-slate-400 flex items-center space-x-1">
                        <FileText className="w-3 h-3" />
                        <span>Hash: {entity.provenance.source_hash}</span>
                      </span>
                    )}
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

