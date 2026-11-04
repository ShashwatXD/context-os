"use client";

import { useEffect, useState } from "react";
import { Database, RefreshCw, CheckCircle2, Clock, AlertCircle } from "lucide-react";
import { api } from "@/lib/api/client";
import { Source } from "@/lib/types/api";

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncingId, setSyncingId] = useState<string | null>(null);

  useEffect(() => {
    loadSources();
  }, []);

  async function loadSources() {
    try {
      const data = await api.getSources();
      setSources(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleSync(sourceId: string) {
    setSyncingId(sourceId);
    try {
      await api.syncSource(sourceId);
      await loadSources();
    } catch (err) {
      console.error(err);
    } finally {
      setSyncingId(null);
    }
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between pb-2 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Enterprise Data Sources</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Connected systems of record with incremental synchronisation and cryptographic provenance.
          </p>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded divide-y divide-slate-100">
        {loading ? (
          <div className="p-8 text-center text-xs text-slate-400">Loading enterprise sources...</div>
        ) : sources.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-400">
            No sources registered. Run <code className="font-mono bg-slate-100 px-1 py-0.5 rounded">python -m app.cli demo seed</code> in the backend.
          </div>
        ) : (
          sources.map((src) => (
            <div key={src.id} className="p-4 flex items-center justify-between hover:bg-slate-50/50 transition-colors">
              <div className="flex items-center space-x-3.5">
                <div className="w-9 h-9 rounded bg-slate-100 flex items-center justify-center text-slate-700 border border-slate-200">
                  <Database className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-semibold text-slate-900">{src.name}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded font-mono bg-slate-100 text-slate-600 border border-slate-200">
                      {src.source_type}
                    </span>
                  </div>
                  <div className="flex items-center space-x-3 text-[11px] text-slate-400 mt-1">
                    <span>ID: <code className="font-mono">{src.id}</code></span>
                    <span>•</span>
                    <span className="flex items-center space-x-1">
                      <Clock className="w-3 h-3" />
                      <span>Last Sync: {src.last_sync_at ? new Date(src.last_sync_at).toLocaleTimeString() : "Never"}</span>
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex items-center space-x-3">
                <span className="flex items-center space-x-1 text-xs text-emerald-600 font-medium">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>Healthy</span>
                </span>
                <button
                  onClick={() => handleSync(src.id)}
                  disabled={syncingId === src.id}
                  className="px-3 py-1.5 border border-slate-200 text-slate-700 text-xs font-medium rounded hover:bg-slate-100 transition-colors flex items-center space-x-1.5"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${syncingId === src.id ? "animate-spin text-slate-400" : ""}`} />
                  <span>{syncingId === src.id ? "Syncing..." : "Sync Now"}</span>
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

