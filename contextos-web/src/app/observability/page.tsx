"use client";

import { useEffect, useState } from "react";
import { Activity, Clock, ShieldAlert, CheckCircle2, ChevronRight, Layers } from "lucide-react";
import { api } from "@/lib/api/client";
import { AgentRun } from "@/lib/types/api";

export default function ObservabilityPage() {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<AgentRun | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadTraces() {
      try {
        const agts = await api.getAgents().catch(() => []);
        if (agts.length > 0) {
          const runList = await api.getAgentRuns(agts[0].id).catch(() => []);
          setRuns(runList);
          if (runList.length > 0) {
            const detail = await api.getTrace(runList[0].id || runList[0].run_id).catch(() => runList[0]);
            setSelectedRun(detail);
          }
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    loadTraces();
  }, []);

  async function handleSelectRun(run: any) {
    const runId = run.id || run.run_id;
    try {
      const detail = await api.getTrace(runId);
      setSelectedRun(detail);
    } catch {
      setSelectedRun(run);
    }
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between pb-2 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">AI Observability & Trace Inspection</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Distributed trace spans, context retrieval provenance, token accounting, and safety checkpoints.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
        {/* Left: Runs List */}
        <div className="md:col-span-4 bg-white border border-slate-200 rounded divide-y divide-slate-100 max-h-[680px] overflow-y-auto">
          {loading ? (
            <div className="p-8 text-center text-xs text-slate-400">Loading execution traces...</div>
          ) : runs.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400">
              No traces found. Run <code className="font-mono bg-slate-100 px-1 py-0.5 rounded">python -m app.cli demo run</code> in the backend.
            </div>
          ) : (
            runs.map((r) => {
              const runId = r.id || r.run_id;
              const isSelected = (selectedRun?.id || selectedRun?.run_id) === runId;
              return (
                <div
                  key={runId}
                  onClick={() => handleSelectRun(r)}
                  className={`p-3.5 cursor-pointer transition-colors ${
                    isSelected ? "bg-slate-100/70" : "hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-semibold text-slate-900">{runId}</span>
                    <span
                      className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-medium ${
                        r.status === "COMPLETED"
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                          : "bg-amber-50 text-amber-700 border border-amber-200"
                      }`}
                    >
                      {r.status}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 line-clamp-1 mt-1">{r.input_prompt}</p>
                  <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono mt-2">
                    <span>{r.latency_ms} ms</span>
                    <span>${r.estimated_cost_usd}</span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Right: Span Waterfall & Detail */}
        <div className="md:col-span-8 bg-white border border-slate-200 rounded p-5 space-y-4">
          {selectedRun ? (
            <>
              <div className="border-b border-slate-100 pb-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-slate-900">
                    Run ID: {selectedRun.id || selectedRun.run_id}
                  </span>
                  <div className="flex space-x-2 text-xs font-mono text-slate-500">
                    <span>Tokens: {selectedRun.total_tokens}</span>
                    <span>•</span>
                    <span>Latency: {selectedRun.latency_ms} ms</span>
                  </div>
                </div>
                <p className="text-xs text-slate-600 mt-1">{selectedRun.input_prompt}</p>
              </div>

              {/* Spans Waterfall List */}
              <div className="space-y-2">
                <h3 className="text-xs font-semibold text-slate-700">Execution Waterfall Spans</h3>
                <div className="border border-slate-200 rounded divide-y divide-slate-100 text-xs">
                  {(selectedRun.spans || []).map((span) => (
                    <div key={span.id} className="p-3 space-y-1.5 bg-slate-50/50">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[11px] font-bold text-slate-800 flex items-center space-x-2">
                          <span className="px-1.5 py-0.5 rounded bg-slate-200 text-slate-700 text-[9px]">
                            {span.span_type}
                          </span>
                          <span>{span.name}</span>
                        </span>
                        <div className="flex items-center space-x-2 font-mono text-[10px]">
                          <span className="text-slate-400">{span.latency_ms} ms</span>
                          <span
                            className={
                              span.status === "SUCCESS"
                                ? "text-emerald-600 font-bold"
                                : "text-amber-600 font-bold"
                            }
                          >
                            [{span.status}]
                          </span>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-2 text-[10px] font-mono text-slate-500 pt-1">
                        <div className="p-2 bg-white rounded border border-slate-200/60 overflow-hidden">
                          <span className="text-slate-400 block mb-0.5">Input Payload:</span>
                          <pre className="truncate">{JSON.stringify(span.input_payload)}</pre>
                        </div>
                        <div className="p-2 bg-white rounded border border-slate-200/60 overflow-hidden">
                          <span className="text-slate-400 block mb-0.5">Output Payload:</span>
                          <pre className="truncate">{JSON.stringify(span.output_payload)}</pre>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="p-12 text-center text-xs text-slate-400">Select an execution trace to inspect spans.</div>
          )}
        </div>
      </div>
    </div>
  );
}

