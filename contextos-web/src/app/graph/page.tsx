"use client";

import { useEffect, useState } from "react";
import { Network, Layers, GitCommit } from "lucide-react";
import { api } from "@/lib/api/client";

export default function ContextGraphPage() {
  const [graphData, setGraphData] = useState<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadGraph() {
      try {
        const data = await api.getGlobalGraph();
        setGraphData(data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    loadGraph();
  }, []);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between pb-2 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Context Graph Exploration</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Topology of all enterprise entities, inferred semantic identities, and data flows.
          </p>
        </div>
        <div className="flex items-center space-x-3 text-xs text-slate-500 font-mono">
          <span>Nodes: {graphData.nodes.length}</span>
          <span>•</span>
          <span>Edges: {graphData.edges.length}</span>
        </div>
      </div>

      {/* Graph Visual Explorer */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
        <div className="md:col-span-8 bg-white border border-slate-200 rounded p-6 min-h-[500px]">
          {loading ? (
            <div className="h-64 flex items-center justify-center text-xs text-slate-400">Loading Context Graph...</div>
          ) : graphData.nodes.length === 0 ? (
            <div className="h-64 flex items-center justify-center text-xs text-slate-400">
              No graph entities discovered yet. Run the demo seed command in the backend.
            </div>
          ) : (
            <div className="space-y-4">
              <div className="text-xs text-slate-500 flex items-center justify-between">
                <span>Enterprise Knowledge Subgraph</span>
                <span className="text-[11px] font-mono text-slate-400">Recursive CTE In-Memory View</span>
              </div>

              {/* Grid representation of graph nodes */}
              <div className="grid grid-cols-2 gap-3 pt-2">
                {graphData.nodes.map((n) => (
                  <div key={n.id} className="p-3.5 border border-slate-200 rounded hover:border-slate-300 transition-colors bg-slate-50/40">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono uppercase text-slate-400 font-semibold">
                        {n.asset_type?.replace("_", " ")}
                      </span>
                      <span className="text-[9px] px-1.5 py-0.5 rounded font-mono bg-emerald-50 text-emerald-700 border border-emerald-200">
                        {n.certification_status}
                      </span>
                    </div>
                    <div className="text-xs font-bold text-slate-900 mt-1 truncate">{n.name}</div>
                    <div className="text-[10px] text-slate-400 font-mono truncate">{n.qualified_name}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right side: Graph Edge Inspector */}
        <div className="md:col-span-4 bg-white border border-slate-200 rounded p-5 space-y-3">
          <h2 className="text-xs font-semibold text-slate-900">Connected Graph Edges</h2>
          <p className="text-[11px] text-slate-500">
            Directed relationships extracted deterministically or inferred via Entity Resolution.
          </p>

          <div className="space-y-2 max-h-[420px] overflow-y-auto pt-2">
            {graphData.edges.map((e) => (
              <div key={e.id} className="p-2.5 border border-slate-100 rounded bg-slate-50/50 text-[11px] space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-slate-200 text-slate-700">
                    {e.type}
                  </span>
                  <span className="text-emerald-600 font-medium text-[10px]">
                    {Math.round((e.confidence || 1.0) * 100)}%
                  </span>
                </div>
                <div className="font-mono text-[10px] text-slate-600 truncate">{e.source}</div>
                <div className="text-[9px] text-slate-400 text-center">↓</div>
                <div className="font-mono text-[10px] text-slate-600 truncate">{e.target}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

