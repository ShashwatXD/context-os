"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { GitFork, ArrowRight, Layers, Database, BarChart2, CheckCircle2, User, RefreshCw } from "lucide-react";
import { api } from "@/lib/api/client";
import { Asset, LineageGraph } from "@/lib/types/api";

function LineageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const queryAssetId = searchParams.get("assetId") || searchParams.get("id") || "";

  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState<string>(queryAssetId);
  const [lineage, setLineage] = useState<LineageGraph | null>(null);
  const [loading, setLoading] = useState(false);

  // Initial Load & Query Param Reaction
  useEffect(() => {
    async function loadInitial() {
      try {
        const asts = await api.getAssets();
        setAssets(asts);

        // Determine target asset ID: URL param takes precedence, else fallback
        let targetId = queryAssetId;
        if (!targetId && asts.length > 0) {
          const defaultAsset =
            asts.find((a) => a.name.includes("revenue") || a.name.includes("mrr")) || asts[0];
          targetId = defaultAsset.id;
        }

        if (targetId) {
          setSelectedAssetId(targetId);
          fetchLineage(targetId);
        }
      } catch (err) {
        console.error("Failed to load catalog assets for lineage:", err);
      }
    }

    loadInitial();
  }, []);

  // React to URL search parameter changes
  useEffect(() => {
    if (queryAssetId && queryAssetId !== selectedAssetId) {
      setSelectedAssetId(queryAssetId);
      fetchLineage(queryAssetId);
    }
  }, [queryAssetId]);

  async function fetchLineage(assetId: string) {
    if (!assetId) return;
    setLoading(true);
    try {
      const data = await api.getLineage(assetId, 3, "both");
      setLineage(data);
    } catch (err) {
      console.error(`Failed to fetch lineage for asset ${assetId}:`, err);
    } finally {
      setLoading(false);
    }
  }

  function handleSelectChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const id = e.target.value;
    setSelectedAssetId(id);
    router.push(`/lineage?assetId=${encodeURIComponent(id)}`);
    fetchLineage(id);
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto font-sans">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-2 border-b border-slate-200 dark:border-slate-800">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100 tracking-tight flex items-center space-x-2">
            <span>Data Lineage Explorer</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
              Multi-Hop Traversal
            </span>
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Trace upstream data provenance and downstream operational consumers across enterprise pipelines.
          </p>
        </div>

        {/* Asset Selector */}
        <div className="flex items-center space-x-2">
          <span className="text-xs font-medium text-slate-600 dark:text-slate-400">Root Focus Anchor:</span>
          <select
            value={selectedAssetId}
            onChange={handleSelectChange}
            className="text-xs border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-1.5 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:border-slate-400 shadow-xs max-w-xs truncate font-mono"
          >
            {/* If query param selected an external or non-standard asset, ensure it appears */}
            {selectedAssetId && !assets.some((a) => a.id === selectedAssetId) && (
              <option value={selectedAssetId}>[FOCUS] {selectedAssetId}</option>
            )}
            {assets.map((a) => (
              <option key={a.id} value={a.id}>
                [{a.asset_type}] {a.name}
              </option>
            ))}
          </select>

          <button
            onClick={() => fetchLineage(selectedAssetId)}
            className="p-1.5 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 rounded-lg text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 shadow-xs"
            title="Reload Lineage"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Lineage Visual Graph Canvas */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 min-h-[480px] shadow-xs">
        {loading ? (
          <div className="h-64 flex flex-col items-center justify-center text-xs text-slate-400 space-y-2">
            <RefreshCw className="w-5 h-5 animate-spin text-slate-400" />
            <span>Traversing recursive graph lineage for {selectedAssetId}...</span>
          </div>
        ) : !lineage || lineage.nodes.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-xs text-slate-400 p-8 text-center space-y-2">
            <GitFork className="w-8 h-8 text-slate-300 dark:text-slate-700" />
            <span>No lineage dependency edges recorded for this asset anchor.</span>
            <span className="text-[11px] font-mono text-slate-400">ID: {selectedAssetId}</span>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 border-b border-slate-100 dark:border-slate-800 pb-3">
              <span className="flex items-center space-x-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                <span>
                  Discovered <strong className="text-slate-800 dark:text-slate-200">{lineage.nodes.length}</strong> connected entities across dependency chain
                </span>
              </span>
              <span className="font-mono text-[11px] text-slate-400 dark:text-slate-500">
                Direction: {lineage.direction} (depth: {lineage.depth})
              </span>
            </div>

            {/* Visual Node Flow Progression */}
            <div className="flex flex-wrap items-center gap-4 py-8 justify-center">
              {lineage.nodes.map((node, index) => {
                const isRoot = node.id === selectedAssetId || node.qualified_name === selectedAssetId;
                const isCertified = node.certification_status === "CERTIFIED";
                const isDisputed = node.certification_status === "DISPUTED";

                return (
                  <div key={node.id} className="flex items-center space-x-3">
                    <div
                      className={`w-64 p-4 rounded-xl border transition-all text-left shadow-xs ${
                        isRoot
                          ? "border-slate-900 dark:border-sky-500 bg-slate-50/80 dark:bg-slate-800/80 ring-2 ring-slate-900/10 dark:ring-sky-500/20 shadow-md"
                          : "border-slate-200 dark:border-slate-750 bg-white dark:bg-slate-850 hover:border-slate-300 dark:hover:border-slate-700"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-mono tracking-wider uppercase text-slate-400 dark:text-slate-400 font-semibold truncate max-w-[140px]">
                          {node.asset_type?.replace("_", " ")}
                        </span>
                        <span
                          className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-medium ${
                            isCertified
                              ? "bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800"
                              : isDisputed
                              ? "bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-800"
                              : "bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800"
                          }`}
                        >
                          {node.certification_status}
                        </span>
                      </div>

                      <div className="text-xs font-bold text-slate-900 dark:text-slate-100 mt-2 truncate" title={node.name}>
                        {node.name}
                      </div>
                      <div className="text-[11px] text-slate-400 dark:text-slate-500 font-mono mt-0.5 truncate" title={node.qualified_name}>
                        {node.qualified_name}
                      </div>

                      <div className="mt-3 pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-[10px] text-slate-500 dark:text-slate-400">
                        <span className="flex items-center space-x-1 truncate max-w-[140px]">
                          <User className="w-3 h-3 text-slate-400 shrink-0" />
                          <span className="truncate">{node.owner_name || "Unassigned"}</span>
                        </span>
                        {isRoot && (
                          <span className="font-semibold text-slate-900 dark:text-sky-400 font-mono text-[9px] bg-slate-200 dark:bg-sky-950/80 px-1.5 py-0.5 rounded border border-slate-300 dark:border-sky-800">
                            [ANCHOR]
                          </span>
                        )}
                      </div>
                    </div>

                    {index < lineage.nodes.length - 1 && (
                      <div className="flex items-center text-slate-300 dark:text-slate-700">
                        <ArrowRight className="w-5 h-5 text-slate-400 dark:text-slate-600" />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Lineage Edges Table */}
            {lineage.edges.length > 0 && (
              <div className="mt-6 pt-4 border-t border-slate-100 dark:border-slate-800">
                <h3 className="text-xs font-semibold text-slate-800 dark:text-slate-200 mb-2.5">
                  Verified Dependency Edges
                </h3>
                <div className="border border-slate-200 dark:border-slate-800 rounded-lg divide-y divide-slate-100 dark:divide-slate-800 text-xs overflow-hidden">
                  {lineage.edges.map((edge) => (
                    <div
                      key={edge.id}
                      className="px-3.5 py-2.5 flex items-center justify-between font-mono text-[11px] bg-white dark:bg-slate-850 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                    >
                      <span className="text-slate-700 dark:text-slate-300 truncate max-w-[260px]">
                        {edge.source}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 text-[10px]">
                        --[{edge.type || edge.relationship_type}]--&gt;
                      </span>
                      <span className="text-slate-700 dark:text-slate-300 truncate max-w-[260px]">
                        {edge.target}
                      </span>
                      <span className="text-emerald-600 dark:text-emerald-400 font-sans font-medium text-xs">
                        {Math.round(edge.confidence * 100)}% Conf
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function LineagePage() {
  return (
    <Suspense
      fallback={
        <div className="p-8 text-center text-xs text-slate-400 flex items-center justify-center space-x-2">
          <RefreshCw className="w-4 h-4 animate-spin text-slate-400" />
          <span>Loading Lineage Explorer...</span>
        </div>
      }
    >
      <LineageContent />
    </Suspense>
  );
}
