"use client";

import { useEffect, useState } from "react";
import { ShieldCheck, Check, X, AlertTriangle, UserCheck } from "lucide-react";
import { api } from "@/lib/api/client";
import { ApprovalItem } from "@/lib/types/api";

export default function GovernancePage() {
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [decidingId, setDecidingId] = useState<string | null>(null);

  useEffect(() => {
    loadApprovals();
  }, []);

  async function loadApprovals() {
    setLoading(true);
    try {
      const data = await api.getApprovals();
      setApprovals(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDecision(requestId: string, decision: "APPROVED" | "REJECTED") {
    setDecidingId(requestId);
    try {
      await api.decideApproval(
        requestId,
        decision,
        "user:enterprise_architect",
        `Human decision executed via Governance Console: ${decision}`
      );
      await loadApprovals();
    } catch (err) {
      console.error(err);
    } finally {
      setDecidingId(null);
    }
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between pb-2 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Governance & Approvals Queue</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Human-in-the-loop review of AI-generated metadata, ambiguous entity resolution matches, and policy updates.
          </p>
        </div>
        <span className="text-xs font-mono text-slate-500 bg-white border border-slate-200 px-3 py-1.5 rounded">
          Pending Reviews: {approvals.length}
        </span>
      </div>

      <div className="bg-white border border-slate-200 rounded divide-y divide-slate-100">
        {loading ? (
          <div className="p-8 text-center text-xs text-slate-400">Loading governance queue...</div>
        ) : approvals.length === 0 ? (
          <div className="p-12 text-center space-y-2">
            <UserCheck className="w-8 h-8 text-emerald-500 mx-auto" />
            <h2 className="text-xs font-semibold text-slate-800">Governance Queue Cleared</h2>
            <p className="text-[11px] text-slate-400">All agent proposals and metric changes have been reviewed and certified.</p>
          </div>
        ) : (
          approvals.map((item) => (
            <div key={item.request_id} className="p-5 space-y-3 hover:bg-slate-50/40 transition-colors">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <span className="text-xs font-bold text-slate-900">{item.asset_name}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded font-mono bg-slate-100 text-slate-600 border border-slate-200">
                    {item.action_type}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded font-mono bg-amber-50 text-amber-700 border border-amber-200">
                    Confidence: {Math.round(item.confidence * 100)}%
                  </span>
                </div>

                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => handleDecision(item.request_id, "APPROVED")}
                    disabled={decidingId === item.request_id}
                    className="px-3 py-1.5 bg-emerald-600 text-white text-xs font-medium rounded hover:bg-emerald-700 transition-colors flex items-center space-x-1"
                  >
                    <Check className="w-3.5 h-3.5" />
                    <span>Approve & Certify</span>
                  </button>
                  <button
                    onClick={() => handleDecision(item.request_id, "REJECTED")}
                    disabled={decidingId === item.request_id}
                    className="px-3 py-1.5 border border-slate-200 text-slate-600 text-xs font-medium rounded hover:bg-slate-100 transition-colors flex items-center space-x-1"
                  >
                    <X className="w-3.5 h-3.5" />
                    <span>Reject</span>
                  </button>
                </div>
              </div>

              <div className="p-3 bg-slate-50 border border-slate-200/60 rounded text-xs text-slate-700 space-y-1">
                <span className="font-semibold text-slate-900 block text-[11px]">Proposed Value:</span>
                <pre className="font-mono text-[11px] text-slate-600 whitespace-pre-wrap">
                  {JSON.stringify(item.proposed_value, null, 2)}
                </pre>
              </div>

              <div className="flex items-center justify-between text-[11px] text-slate-400">
                <span>Reason: {item.reasoning}</span>
                <span>Requested by: <code className="font-mono text-slate-600">{item.requested_by}</code></span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

