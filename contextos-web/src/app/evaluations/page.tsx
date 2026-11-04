"use client";

import { useEffect, useState } from "react";
import { BarChart3, Play, CheckCircle2, ShieldCheck, Clock, DollarSign } from "lucide-react";
import { api } from "@/lib/api/client";
import { EvaluationRun } from "@/lib/types/api";

export default function EvaluationsPage() {
  const [evalRuns, setEvalRuns] = useState<EvaluationRun[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadEvaluations();
  }, []);

  async function loadEvaluations() {
    try {
      const data = await api.getEvaluations();
      setEvalRuns(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleTriggerRun() {
    setIsRunning(true);
    try {
      await api.runEvaluation();
      await loadEvaluations();
    } catch (err) {
      console.error(err);
    } finally {
      setIsRunning(false);
    }
  }

  const latest = evalRuns[0];

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between pb-2 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">AI Evaluations & Regression Benchmarks</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Empirical benchmark metrics against golden datasets measuring Recall@K, Context Relevance, and Policy Compliance.
          </p>
        </div>

        <button
          onClick={handleTriggerRun}
          disabled={isRunning}
          className="px-3.5 py-2 bg-slate-900 text-white text-xs font-medium rounded hover:bg-slate-800 transition-colors flex items-center space-x-1.5"
        >
          <Play className="w-3.5 h-3.5" />
          <span>{isRunning ? "Running Benchmark..." : "Run Golden Benchmark"}</span>
        </button>
      </div>

      {/* Benchmark Metric Cards */}
      {latest && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="p-4 bg-white border border-slate-200 rounded">
            <span className="text-xs font-medium text-slate-500">Retrieval Recall@5</span>
            <div className="text-2xl font-bold text-slate-900 mt-2">
              {Math.round(latest.overall_recall_at_k * 100)}%
            </div>
            <div className="text-[11px] text-emerald-600 font-medium mt-1">Grounded entity match</div>
          </div>

          <div className="p-4 bg-white border border-slate-200 rounded">
            <span className="text-xs font-medium text-slate-500">Context Relevance</span>
            <div className="text-2xl font-bold text-slate-900 mt-2">
              {Math.round(latest.overall_context_relevance * 100)}%
            </div>
            <div className="text-[11px] text-slate-400 mt-1">RRF fusion ranking score</div>
          </div>

          <div className="p-4 bg-white border border-slate-200 rounded">
            <span className="text-xs font-medium text-slate-500">Policy Compliance</span>
            <div className="text-2xl font-bold text-slate-900 mt-2">
              {Math.round(latest.policy_compliance_rate * 100)}%
            </div>
            <div className="text-[11px] text-emerald-600 font-medium mt-1">Safety & gate adherence</div>
          </div>

          <div className="p-4 bg-white border border-slate-200 rounded">
            <span className="text-xs font-medium text-slate-500">Average Latency</span>
            <div className="text-2xl font-bold text-slate-900 mt-2">
              {latest.average_latency_ms} ms
            </div>
            <div className="text-[11px] text-slate-400 mt-1">Sub-second execution</div>
          </div>
        </div>
      )}

      {/* Evaluation Runs History */}
      <div className="bg-white border border-slate-200 rounded p-5 space-y-4">
        <h2 className="text-xs font-semibold text-slate-900">Benchmark Execution History</h2>

        <div className="border border-slate-200 rounded divide-y divide-slate-100 text-xs">
          {loading ? (
            <div className="p-8 text-center text-xs text-slate-400">Loading evaluation benchmarks...</div>
          ) : evalRuns.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400">
              No evaluation runs recorded yet. Click &quot;Run Golden Benchmark&quot; to execute.
            </div>
          ) : (
            evalRuns.map((r) => (
              <div key={r.id} className="p-4 flex items-center justify-between hover:bg-slate-50/50">
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span className="font-mono text-xs font-bold text-slate-900">{r.id}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded font-mono bg-slate-100 text-slate-600 border border-slate-200">
                      {r.dataset_id} v{r.dataset_version}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded font-mono bg-emerald-50 text-emerald-700 border border-emerald-200">
                      {r.model_version}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-400">
                    Executed at: {new Date(r.executed_at).toLocaleString()}
                  </div>
                </div>

                <div className="flex items-center space-x-6 text-right font-mono text-xs">
                  <div>
                    <span className="text-slate-400 text-[10px] block">Recall@5</span>
                    <span className="font-bold text-slate-900">{Math.round(r.overall_recall_at_k * 100)}%</span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-[10px] block">Compliance</span>
                    <span className="font-bold text-emerald-600">{Math.round(r.policy_compliance_rate * 100)}%</span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-[10px] block">Latency</span>
                    <span className="text-slate-700">{r.average_latency_ms} ms</span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

