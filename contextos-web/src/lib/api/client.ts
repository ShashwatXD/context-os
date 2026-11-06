import {
  Asset,
  ContextResponse,
  DeadLetterRecord,
  EvaluationRun,
  LineageGraph,
  Source,
  SyncCheckpoint,
  ApprovalItem,
  AgentRun,
} from "../types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options?.headers || {}),
      },
      cache: "no-store",
    });

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.message || `API error ${res.status}: ${res.statusText}`);
    }

    return await res.json();
  } catch (err: any) {
    console.warn(`[API Client] Failed fetch from ${url}:`, err.message);
    throw err;
  }
}

export const api = {
  // Health
  getHealth: () => fetchJson<{ status: string; version: string; database: string }>("/health"),

  // Sources
  getSources: () => fetchJson<Source[]>("/sources"),
  syncSource: (sourceId: string) =>
    fetchJson<any>(`/sources/${sourceId}/sync`, { method: "POST" }),
  getCheckpoint: (sourceId: string) =>
    fetchJson<SyncCheckpoint | null>(`/sources/${sourceId}/checkpoint`),
  getDeadLetters: (sourceId?: string) => {
    const q = sourceId ? `?source_id=${sourceId}` : "";
    return fetchJson<DeadLetterRecord[]>(`/sources/dlq/records${q}`);
  },

  // Catalog Assets & Lineage
  getAssets: (params?: { query?: string; type?: string; certification?: string }) => {
    const q = new URLSearchParams();
    if (params?.query) q.set("query", params.query);
    if (params?.type) q.set("asset_type", params.type);
    if (params?.certification) q.set("certification", params.certification);
    return fetchJson<Asset[]>(`/assets?${q.toString()}`);
  },
  getAsset: (id: string) => fetchJson<Asset>(`/assets/${id}`),
  getLineage: (id: string, depth = 3, direction = "both") =>
    fetchJson<LineageGraph>(`/assets/${id}/lineage?depth=${depth}&direction=${direction}`),

  // Global Context Graph
  getGlobalGraph: (limit = 100) => fetchJson<{ nodes: any[]; edges: any[] }>(`/graph?limit=${limit}`),

  // Context Query
  queryContext: (payload: { query: string; top_k?: number; asset_types?: string[] }) =>
    fetchJson<ContextResponse>("/context/query", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Governance & Approvals
  getApprovals: () => fetchJson<ApprovalItem[]>("/approvals"),
  decideApproval: (requestId: string, decision: "APPROVED" | "REJECTED", reviewerId: string, notes?: string) =>
    fetchJson<any>(`/approvals/${requestId}/decide`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        reviewer_id: reviewerId,
        decision_notes: notes,
      }),
    }),

  // Agents & Traces
  getAgents: () => fetchJson<any[]>("/agents"),
  runAgent: (agentId: string, payload: { user_prompt: string; tool_sequence?: any[] }) =>
    fetchJson<{
      run_id: string;
      status: string;
      output_response: string;
      latency_ms: number;
      total_tokens: number;
      retrieved_context_ids: string[];
      spans_count: number;
    }>(`/agents/${agentId}/run`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getAgentRuns: (agentId: string) => fetchJson<AgentRun[]>(`/agents/${agentId}/runs`),
  getTrace: (runId: string) => fetchJson<AgentRun>(`/traces/${runId}`),

  // Evaluations
  getEvaluations: () => fetchJson<EvaluationRun[]>("/evaluations"),
  runEvaluation: (modelVersion = "contextos-hybrid-v1.0") =>
    fetchJson<any>("/evaluations/run", {
      method: "POST",
      body: JSON.stringify({ model_version: modelVersion }),
    }),
};

