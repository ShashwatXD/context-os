"use client";

import { useEffect, useState } from "react";
import { Bot, Shield, Terminal, Play, CheckCircle2, Clock } from "lucide-react";
import { api } from "@/lib/api/client";

export default function AgentsPage() {
  const [agents, setAgents] = useState<any[]>([]);
  const [runs, setRuns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadAgents() {
      try {
        const agts = await api.getAgents();
        setAgents(agts);
        if (agts.length > 0) {
          const runList = await api.getAgentRuns(agts[0].id).catch(() => []);
          setRuns(runList);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    loadAgents();
  }, []);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between pb-2 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Context Enrichment Agents</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Autonomous metadata stewards operating under strict tool-level permissions and human approval gates.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Agent Registry Card */}
        {agents.map((agt) => (
          <div key={agt.id} className="p-5 bg-white border border-slate-200 rounded space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2.5">
                <div className="w-8 h-8 rounded bg-slate-100 flex items-center justify-center text-slate-800 border border-slate-200">
                  <Bot className="w-4 h-4" />
                </div>
                <div>
                  <h2 className="text-xs font-bold text-slate-900">{agt.name}</h2>
                  <span className="text-[10px] text-slate-400 font-mono">v{agt.version} • {agt.id}</span>
                </div>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded font-mono font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                ACTIVE
              </span>
            </div>

            <div className="space-y-1">
              <span className="text-[11px] font-semibold text-slate-700">Role & Responsibilities</span>
              <p className="text-xs text-slate-600 bg-slate-50 p-2.5 rounded border border-slate-100">
                {agt.role}
              </p>
            </div>

            <div className="space-y-1">
              <span className="text-[11px] font-semibold text-slate-700">Permitted MCP Tools</span>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {agt.allowed_tools.map((t: string) => (
                  <span
                    key={t}
                    className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200 flex items-center space-x-1"
                  >
                    <Terminal className="w-2.5 h-2.5 text-slate-400" />
                    <span>{t}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Execution History */}
      <div className="bg-white border border-slate-200 rounded p-5 space-y-4">
        <h2 className="text-xs font-semibold text-slate-900">Recent Execution Runs</h2>
        <div className="border border-slate-200 rounded divide-y divide-slate-100 text-xs">
          {runs.length === 0 ? (
            <div className="p-6 text-center text-xs text-slate-400">
              No recent runs recorded. Run <code className="font-mono bg-slate-100 px-1 py-0.5 rounded">python -m app.cli demo run</code> in the backend.
            </div>
          ) : (
            runs.map((r) => (
              <div key={r.id} className="p-3.5 flex items-center justify-between hover:bg-slate-50/50">
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span className="font-mono text-xs text-slate-800 font-semibold">{r.id}</span>
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
                  <p className="text-xs text-slate-600 line-clamp-1">{r.input_prompt}</p>
                </div>

                <div className="text-right text-[11px] text-slate-400 font-mono space-y-0.5">
                  <div>{r.latency_ms} ms • {r.total_tokens} tokens</div>
                  <div className="text-slate-500">${r.estimated_cost_usd} USD</div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

