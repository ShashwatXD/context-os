"use client";

import { useEffect, useState } from "react";
import {
  Database,
  RefreshCw,
  CheckCircle2,
  Clock,
  AlertCircle,
  GitBranch,
  MessageSquare,
  BookOpen,
  FileCode,
  ShieldCheck,
  Radio,
  Layers,
  ArrowRight,
  Archive,
} from "lucide-react";
import { api } from "@/lib/api/client";
import { DeadLetterRecord, Source, SyncCheckpoint } from "@/lib/types/api";

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"sources" | "dlq">("sources");
  const [deadLetters, setDeadLetters] = useState<DeadLetterRecord[]>([]);
  const [loadingDlq, setLoadingDlq] = useState(false);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);

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

  async function loadDeadLetters() {
    setLoadingDlq(true);
    try {
      const data = await api.getDeadLetters();
      setDeadLetters(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingDlq(false);
    }
  }

  function handleTabChange(tab: "sources" | "dlq") {
    setActiveTab(tab);
    if (tab === "dlq") {
      loadDeadLetters();
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

  function getSourceIcon(type: string) {
    switch (type.toUpperCase()) {
      case "POSTGRESQL":
      case "SNOWFLAKE":
        return <Database className="w-4 h-4 text-sky-600" />;
      case "GITHUB":
        return <GitBranch className="w-4 h-4 text-purple-600" />;
      case "SLACK":
        return <MessageSquare className="w-4 h-4 text-amber-600" />;
      case "DBT":
        return <FileCode className="w-4 h-4 text-emerald-600" />;
      case "NOTION":
        return <BookOpen className="w-4 h-4 text-slate-700" />;
      default:
        return <Layers className="w-4 h-4 text-slate-600" />;
    }
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between pb-2 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Enterprise Data Sources</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Connected enterprise systems of record with incremental synchronisation, cursors, DLQ, and cryptographic provenance.
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={() => handleTabChange("sources")}
            className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
              activeTab === "sources"
                ? "bg-slate-900 text-white"
                : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-50"
            }`}
          >
            Connected Systems ({sources.length})
          </button>
          <button
            onClick={() => handleTabChange("dlq")}
            className={`px-3 py-1.5 text-xs font-medium rounded transition-colors flex items-center space-x-1.5 ${
              activeTab === "dlq"
                ? "bg-slate-900 text-white"
                : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-50"
            }`}
          >
            <Archive className="w-3.5 h-3.5" />
            <span>Dead-Letter Queue (DLQ)</span>
          </button>
        </div>
      </div>

      {/* Mechanism Architecture Banners */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="bg-white border border-slate-200 rounded p-3.5 flex items-start space-x-3">
          <div className="w-8 h-8 rounded bg-sky-50 border border-sky-200 text-sky-700 flex items-center justify-center shrink-0">
            <RefreshCw className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-900">Mechanism A: Background Sync</div>
            <div className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
              Incremental cursor-based sync with deduplication, retries, and dead-letter handling.
            </div>
            <div className="mt-1.5 inline-flex items-center space-x-1 text-[10px] font-mono text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span>Active Daemon</span>
            </div>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded p-3.5 flex items-start space-x-3">
          <div className="w-8 h-8 rounded bg-purple-50 border border-purple-200 text-purple-700 flex items-center justify-center shrink-0">
            <Radio className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-900">Mechanism B: On-Demand Context</div>
            <div className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
              Standard agent query interface via Model Context Protocol (MCP) and REST APIs.
            </div>
            <div className="mt-1.5 inline-flex items-center space-x-1 text-[10px] font-mono text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded border border-purple-200">
              <span>7 MCP Tools Exposed</span>
            </div>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded p-3.5 flex items-start space-x-3">
          <div className="w-8 h-8 rounded bg-amber-50 border border-amber-200 text-amber-700 flex items-center justify-center shrink-0">
            <ShieldCheck className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-900">Mechanism C: Live Fallback</div>
            <div className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
              Triggers live connector fetch on staleness (&gt;threshold) or cache miss before answering.
            </div>
            <div className="mt-1.5 inline-flex items-center space-x-1 text-[10px] font-mono text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
              <span>Freshness Threshold: 900s</span>
            </div>
          </div>
        </div>
      </div>

      {activeTab === "sources" ? (
        /* Sources Table / List */
        <div className="bg-white border border-slate-200 rounded divide-y divide-slate-100">
          {loading ? (
            <div className="p-8 text-center text-xs text-slate-400">Loading enterprise sources...</div>
          ) : sources.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400">
              No sources registered. Run <code className="font-mono bg-slate-100 px-1 py-0.5 rounded">python -m app.cli demo seed</code> in the backend.
            </div>
          ) : (
            sources.map((src) => (
              <div key={src.id} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-slate-50/50 transition-colors">
                <div className="flex items-start space-x-3.5">
                  <div className="w-9 h-9 rounded bg-slate-50 flex items-center justify-center border border-slate-200 shrink-0">
                    {getSourceIcon(src.source_type)}
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-semibold text-slate-900">{src.name}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded font-mono bg-slate-100 text-slate-600 border border-slate-200">
                        {src.source_type}
                      </span>
                      {src.auth_type && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded font-mono bg-sky-50 text-sky-700 border border-sky-200">
                          {src.auth_type}
                        </span>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400 mt-1">
                      <span>ID: <code className="font-mono text-slate-600">{src.id}</code></span>
                      <span>•</span>
                      <span className="flex items-center space-x-1">
                        <Clock className="w-3 h-3" />
                        <span>Last Sync: {src.last_sync_at ? new Date(src.last_sync_at).toLocaleString() : "Never"}</span>
                      </span>
                      <span>•</span>
                      <span>Freshness SLA: <code className="font-mono text-slate-600">{src.freshness_threshold_seconds || 900}s</code></span>
                    </div>

                    {src.oauth_scopes && src.oauth_scopes.length > 0 && (
                      <div className="mt-2 flex items-center space-x-1.5 text-[10px]">
                        <span className="text-slate-400">Scopes:</span>
                        {src.oauth_scopes.map((scope) => (
                          <span key={scope} className="px-1.5 py-0.2 font-mono bg-slate-100 text-slate-600 rounded">
                            {scope}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center space-x-3 self-end md:self-center">
                  <span className="flex items-center space-x-1 text-xs text-emerald-600 font-medium bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>{src.last_sync_status || "HEALTHY"}</span>
                  </span>
                  <button
                    onClick={() => handleSync(src.id)}
                    disabled={syncingId === src.id}
                    className="px-3 py-1.5 border border-slate-200 text-slate-700 text-xs font-medium rounded hover:bg-slate-100 transition-colors flex items-center space-x-1.5 bg-white shadow-sm"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${syncingId === src.id ? "animate-spin text-slate-400" : ""}`} />
                    <span>{syncingId === src.id ? "Syncing..." : "Sync Now"}</span>
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      ) : (
        /* Dead-Letter Queue Inspection */
        <div className="bg-white border border-slate-200 rounded p-4 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                Dead-Letter Queue (DLQ) Records
              </h2>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Ingestion records that failed validation or parsing after max retries are safely quarantined here.
              </p>
            </div>
            <button
              onClick={loadDeadLetters}
              className="px-2.5 py-1 text-xs border border-slate-200 rounded text-slate-600 hover:bg-slate-50 flex items-center space-x-1"
            >
              <RefreshCw className={`w-3 h-3 ${loadingDlq ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>

          {loadingDlq ? (
            <div className="p-8 text-center text-xs text-slate-400">Loading DLQ records...</div>
          ) : deadLetters.length === 0 ? (
            <div className="p-8 text-center text-xs text-emerald-600 bg-emerald-50/50 border border-dashed border-emerald-200 rounded">
              <CheckCircle2 className="w-5 h-5 mx-auto mb-1 text-emerald-500" />
              <span>All clear. No quarantined records in the Dead-Letter Queue.</span>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {deadLetters.map((dlq) => (
                <div key={dlq.id} className="py-3 text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <span className="font-mono text-slate-900 font-semibold">{dlq.raw_record_id}</span>
                      <span className="px-1.5 py-0.5 text-[10px] bg-rose-50 text-rose-700 border border-rose-200 rounded font-mono">
                        Retries: {dlq.retry_count}
                      </span>
                      <span className="text-slate-400 font-mono text-[10px]">Source: {dlq.source_id}</span>
                    </div>
                    <span className="text-slate-400 text-[10px]">
                      {new Date(dlq.failed_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="text-rose-600 text-[11px] font-mono bg-rose-50/50 p-1.5 rounded border border-rose-100">
                    Reason: {dlq.error_reason}
                  </div>
                  <pre className="text-[10px] font-mono bg-slate-900 text-slate-100 p-2 rounded overflow-x-auto max-h-32">
                    {JSON.stringify(dlq.payload, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
