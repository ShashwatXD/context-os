"use client";

import { useEffect, useState } from "react";
import {
  Bot,
  Shield,
  Terminal,
  Play,
  CheckCircle2,
  Clock,
  Sparkles,
  Cpu,
  Coins,
  Activity,
  Layers,
  ArrowRight,
} from "lucide-react";
import { api } from "@/lib/api/client";

const SUGGESTED_PROMPTS = [
  "Audit stripe charges and check for discrepancy with revenue policy",
  "Trace upstream dependencies of fct_monthly_revenue and verify compliance",
  "Inspect unclassified postgres customer records and propose PII tags",
];

export default function AgentsPage() {
  const [agents, setAgents] = useState<any[]>([]);
  const [runs, setRuns] = useState<any[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("");
  const [userPrompt, setUserPrompt] = useState<string>(SUGGESTED_PROMPTS[0]);
  const [isRunning, setIsRunning] = useState(false);
  const [lastRunResult, setLastRunResult] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadAgents() {
      try {
        const agts = await api.getAgents();
        setAgents(agts);
        if (agts.length > 0) {
          setSelectedAgentId(agts[0].id);
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

  async function handleExecuteAgent(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedAgentId || !userPrompt.trim()) return;

    setIsRunning(true);
    try {
      const result = await api.runAgent(selectedAgentId, {
        user_prompt: userPrompt,
      });
      setLastRunResult(result);

      // Refresh runs list
      const updatedRuns = await api.getAgentRuns(selectedAgentId).catch(() => []);
      setRuns(updatedRuns);
    } catch (err) {
      console.error(err);
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">
              Autonomous Context Agents
            </h1>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800 flex items-center space-x-1">
              <Cpu className="w-3 h-3 text-emerald-500" />
              <span>MCP & Tool-Governed</span>
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Autonomous metadata stewards operating under strict tool-level permissions, cryptographic audit spans, and human approval gates.
          </p>
        </div>
      </div>

      {/* Agent Interactive Execution Sandbox */}
      <div className="p-5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Sparkles className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
            <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Trigger Autonomous Agent Run
            </h2>
          </div>
          <span className="text-[11px] font-mono text-slate-400 dark:text-slate-500">
            POST /api/v1/agents/{selectedAgentId || "{id}"}/run
          </span>
        </div>

        <form onSubmit={handleExecuteAgent} className="space-y-3">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="sm:w-1/3">
              <label className="text-[11px] font-medium text-slate-600 dark:text-slate-400 block mb-1">
                Target Steward Agent
              </label>
              <select
                value={selectedAgentId}
                onChange={(e) => {
                  setSelectedAgentId(e.target.value);
                  api.getAgentRuns(e.target.value).then(setRuns).catch(() => {});
                }}
                className="w-full px-3 py-2 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 rounded text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:border-slate-400"
              >
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.id})
                  </option>
                ))}
              </select>
            </div>

            <div className="flex-1">
              <label className="text-[11px] font-medium text-slate-600 dark:text-slate-400 block mb-1">
                Instruction / Audit Prompt
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={userPrompt}
                  onChange={(e) => setUserPrompt(e.target.value)}
                  placeholder="Enter instruction for autonomous agent..."
                  className="w-full pl-3 pr-28 py-2 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 rounded text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:border-slate-400"
                />
                <button
                  type="submit"
                  disabled={isRunning || !selectedAgentId}
                  className="absolute right-1 top-1 bottom-1 px-3 bg-slate-900 dark:bg-indigo-600 text-white text-xs font-medium rounded hover:bg-slate-800 dark:hover:bg-indigo-500 transition-colors flex items-center space-x-1 disabled:opacity-50"
                >
                  <Play className="w-3 h-3 fill-white" />
                  <span>{isRunning ? "Running..." : "Run Agent"}</span>
                </button>
              </div>
            </div>
          </div>

          {/* Quick preset chips */}
          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <span className="text-[10px] text-slate-400 dark:text-slate-500 font-medium">Quick Prompts:</span>
            {SUGGESTED_PROMPTS.map((p, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => setUserPrompt(p)}
                className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors border border-slate-200/60 dark:border-slate-700"
              >
                {p}
              </button>
            ))}
          </div>
        </form>

        {/* Live Run Output */}
        {lastRunResult && (
          <div className="mt-4 p-4 rounded border border-indigo-200 dark:border-indigo-900/60 bg-indigo-50/40 dark:bg-indigo-950/20 space-y-3">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center space-x-2">
                <span className="font-mono font-bold text-slate-900 dark:text-slate-100">
                  {lastRunResult.run_id}
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800 font-semibold">
                  {lastRunResult.status}
                </span>
              </div>
              <div className="flex items-center space-x-3 text-[11px] font-mono text-slate-500 dark:text-slate-400">
                <span className="flex items-center space-x-1">
                  <Clock className="w-3 h-3 text-slate-400" />
                  <span>{lastRunResult.latency_ms} ms</span>
                </span>
                <span className="flex items-center space-x-1">
                  <Activity className="w-3 h-3 text-slate-400" />
                  <span>{lastRunResult.total_tokens} tokens</span>
                </span>
                <span className="flex items-center space-x-1">
                  <Layers className="w-3 h-3 text-slate-400" />
                  <span>{lastRunResult.retrieved_context_ids?.length || 0} assets context</span>
                </span>
              </div>
            </div>

            <div className="bg-white dark:bg-slate-900 p-3 rounded border border-slate-200 dark:border-slate-800 text-xs text-slate-800 dark:text-slate-200 leading-relaxed font-sans">
              <div className="text-[10px] uppercase font-bold text-slate-400 dark:text-slate-500 mb-1">
                Agent Synthesized Output & Plan
              </div>
              {lastRunResult.output_response}
            </div>
          </div>
        )}
      </div>

      {/* Agent Registry Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {agents.map((agt) => (
          <div
            key={agt.id}
            className={`p-5 bg-white dark:bg-slate-900 border rounded space-y-4 ${
              selectedAgentId === agt.id
                ? "border-indigo-400 dark:border-indigo-500 shadow-sm"
                : "border-slate-200 dark:border-slate-800"
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2.5">
                <div className="w-8 h-8 rounded bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-700">
                  <Bot className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                </div>
                <div>
                  <h2 className="text-xs font-bold text-slate-900 dark:text-slate-100">{agt.name}</h2>
                  <span className="text-[10px] text-slate-400 dark:text-slate-500 font-mono">
                    v{agt.version} • {agt.id}
                  </span>
                </div>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded font-mono font-medium bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                ACTIVE
              </span>
            </div>

            <div className="space-y-1">
              <span className="text-[11px] font-semibold text-slate-700 dark:text-slate-300">
                Role & Responsibilities
              </span>
              <p className="text-xs text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-800/60 p-2.5 rounded border border-slate-100 dark:border-slate-800">
                {agt.role}
              </p>
            </div>

            <div className="space-y-1">
              <span className="text-[11px] font-semibold text-slate-700 dark:text-slate-300">
                Permitted MCP Tools
              </span>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {agt.allowed_tools.map((t: string) => (
                  <span
                    key={t}
                    className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 flex items-center space-x-1"
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
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded p-5 space-y-4">
        <h2 className="text-xs font-semibold text-slate-900 dark:text-slate-100">Recent Execution Runs</h2>
        <div className="border border-slate-200 dark:border-slate-800 rounded divide-y divide-slate-100 dark:divide-slate-800 text-xs">
          {runs.length === 0 ? (
            <div className="p-6 text-center text-xs text-slate-400 dark:text-slate-500">
              No recent runs recorded. Use the sandbox above to trigger a test run.
            </div>
          ) : (
            runs.map((r) => (
              <div
                key={r.id}
                className="p-3.5 flex items-center justify-between hover:bg-slate-50/50 dark:hover:bg-slate-800/30 transition-colors"
              >
                <div className="space-y-1 max-w-2xl">
                  <div className="flex items-center space-x-2">
                    <span className="font-mono text-xs text-slate-800 dark:text-slate-200 font-semibold">
                      {r.id}
                    </span>
                    <span
                      className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-medium ${
                        r.status === "COMPLETED"
                          ? "bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800"
                          : "bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800"
                      }`}
                    >
                      {r.status}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-1">{r.input_prompt}</p>
                  {r.output_response && (
                    <p className="text-[11px] text-slate-500 dark:text-slate-400 line-clamp-1 italic">
                      "{r.output_response}"
                    </p>
                  )}
                </div>

                <div className="text-right text-[11px] text-slate-400 dark:text-slate-500 font-mono space-y-0.5 shrink-0 pl-4">
                  <div>
                    {r.latency_ms} ms • {r.total_tokens} tokens
                  </div>
                  <div className="text-slate-500 dark:text-slate-400">${r.estimated_cost_usd} USD</div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
