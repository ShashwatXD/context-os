"use client";

import { useEffect, useState } from "react";
import { GitFork, ArrowRight, Layers, Database, BarChart2 } from "lucide-react";
import { api } from "@/lib/api/client";
import { Asset, LineageGraph } from "@/lib/types/api";

export default function LineagePage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState<string>("");
  const [lineage, setLineage] = useState<LineageGraph | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function init() {
      try {
        const asts = await api.getAssets();
        setAssets(asts);
        if (asts.length > 0) {
          // Default to a transformation model or table
          const target = asts.find((a) => a.name.includes("revenue") || a.name.includes("mrr")) || asts[0];
          setSelectedAssetId(target.id);
          fetchLineage(target.id);
        }
      } catch (err) {
        console.error(err);
      }
    }
    init();
  }, []);

  async function fetchLineage(assetId: string) {
    setLoading(true);
    try {
      const data = await api.getLineage(assetId, 3, "both");
      setLineage(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  function handleSelectChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const id = e.target.value;
    setSelectedAssetId(id);
    fetchLineage(id);
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between pb-2 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Data Lineage Explorer</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Trace multi-hop upstream and downstream dependencies from raw sources to BI dashboards.
          </p>
        </div>

        {/* Asset Selector */}
        <div className="flex items-center space-x-2">
          <span className="text-xs font-medium text-slate-600">Root Anchor:</span>
          <select
            value={selectedAssetId}
            onChange={handleSelectChange}
            className="text-xs border border-slate-200 rounded px-3 py-1.5 bg-white text-slate-800 focus:outline-none focus:border-slate-400"
          >
            {assets.map((a) => (
              <option key={a.id} value={a.id}>
                [{a.asset_type}] {a.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Lineage Visual Graph Canvas */}
      <div className="bg-white border border-slate-200 rounded p-6 min-h-[480px]">
        {loading ? (
          <div className="h-64 flex items-center justify-center text-xs text-slate-400">
            Traversing recursive graph lineage...
          </div>
        ) : !lineage || lineage.nodes.length === 0 ? (
          <div className="h-64 flex items-center justify-center text-xs text-slate-400">
            No lineage edges recorded for this asset yet.
          </div>
        ) : (
          <div className="space-y-6">
            <div className="flex items-center justify-between text-xs text-slate-500 border-b border-slate-100 pb-3">
              <span>Discovered {lineage.nodes.length} connected entities across dependency chain</span>
              <span className="font-mono text-[11px] text-slate-400">
                Direction: {lineage.direction} (depth: {lineage.depth})
              </span>
            </div>

            {/* Visual Node Flow Progression */}
            <div className="flex flex-wrap items-center gap-4 py-8 justify-center">
              {lineage.nodes.map((node, index) => {
                const isRoot = node.id === selectedAssetId;
                return (
                  <div key={node.id} className="flex items-center space-x-3">
                    <div
                      className={`w-60 p-4 rounded border transition-all ${
                        isRoot
                          ? "border-slate-900 bg-slate-50/80 shadow-sm"
                          : "border-slate-200 bg-white hover:border-slate-300"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-mono tracking-wider uppercase text-slate-400 font-semibold">
                          {node.asset_type.replace("_", " ")}
                        </span>
                        <span
                          className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-medium ${
                            node.certification_status === "CERTIFIED"
                              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                              : "bg-amber-50 text-amber-700 border border-amber-200"
                          }`}
                        >
                          {node.certification_status}
                        </span>
                      </div>

                      <div className="text-xs font-bold text-slate-900 mt-2 truncate">
                        {node.name}
                      </div>
                      <div className="text-[11px] text-slate-400 font-mono mt-0.5 truncate">
                        {node.qualified_name}
                      </div>

                      <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-500">
                        <span>Owner: {node.owner_name || "Unassigned"}</span>
                        {isRoot && <span className="font-semibold text-slate-800">[Focus]</span>}
                      </div>
                    </div>

                    {index < lineage.nodes.length - 1 && (
                      <div className="flex items-center text-slate-300">
                        <ArrowRight className="w-5 h-5 text-slate-400" />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Lineage Edges Table */}
            {lineage.edges.length > 0 && (
              <div className="mt-6 pt-4 border-t border-slate-100">
                <h3 className="text-xs font-semibold text-slate-700 mb-2">Verified Dependency Edges</h3>
                <div className="border border-slate-200 rounded divide-y divide-slate-100 text-xs">
                  {lineage.edges.map((edge) => (
                    <div key={edge.id} className="px-3.5 py-2 flex items-center justify-between font-mono text-[11px]">
                      <span className="text-slate-700 truncate max-w-[240px]">{edge.source}</span>
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                        --[{edge.type || edge.relationship_type}]--&gt;
                      </span>
                      <span className="text-slate-700 truncate max-w-[240px]">{edge.target}</span>
                      <span className="text-emerald-600 font-sans font-medium text-xs">
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

