"use client";

import { KeyRound, Terminal, CheckCircle2, Copy } from "lucide-react";
import { useState } from "react";

const MCP_TOOLS = [
  {
    name: "search_assets",
    description: "Search enterprise metadata catalog using hybrid lexical and vector retrieval.",
    parameters: "{ query: string, asset_type?: string, limit?: number }",
  },
  {
    name: "get_asset_details",
    description: "Retrieve verified technical metadata, columns, and certification status.",
    parameters: "{ asset_id: string }",
  },
  {
    name: "get_lineage",
    description: "Traverse multi-hop dependency graph upstream and downstream with evidence.",
    parameters: "{ asset_id: string, depth?: number, direction?: 'upstream' | 'downstream' | 'both' }",
  },
  {
    name: "search_context",
    description: "High-level context query returning matched entities, lineage, and conflicting definitions.",
    parameters: "{ query: string, asset_types?: string[] }",
  },
  {
    name: "get_business_definition",
    description: "Look up certified business glossary definitions and disputed metric formulas.",
    parameters: "{ term: string }",
  },
  {
    name: "get_asset_owner",
    description: "Identify verified technical and business owners, team channels, and certification.",
    parameters: "{ asset_id: string }",
  },
];

export default function AgentAccessPage() {
  const [copied, setCopied] = useState(false);

  const mcpConfig = JSON.stringify(
    {
      mcpServers: {
        contextos: {
          command: "python",
          args: ["-m", "app.infrastructure.mcp.server"],
          env: {
            API_TOKEN: "demo-contextos-token",
          },
        },
      },
    },
    null,
    2
  );

  function handleCopy() {
    navigator.clipboard.writeText(mcpConfig);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between pb-2 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Agent Access & Model Context Protocol (MCP)</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Expose verifiable enterprise context to external LLM agents (Claude Desktop, LangChain, Cursor) with zero raw SQL access.
          </p>
        </div>
      </div>

      {/* Integration Instructions */}
      <div className="p-5 bg-white border border-slate-200 rounded space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xs font-semibold text-slate-900">Claude Desktop / MCP Client Configuration</h2>
            <p className="text-xs text-slate-500 mt-0.5">Add to your claude_desktop_config.json to grant verified enterprise context.</p>
          </div>
          <button
            onClick={handleCopy}
            className="px-3 py-1.5 border border-slate-200 text-slate-700 text-xs font-medium rounded hover:bg-slate-50 transition-colors flex items-center space-x-1"
          >
            <Copy className="w-3.5 h-3.5 text-slate-400" />
            <span>{copied ? "Copied!" : "Copy Config"}</span>
          </button>
        </div>

        <pre className="p-3 bg-slate-900 text-slate-100 rounded text-xs font-mono overflow-x-auto">
          {mcpConfig}
        </pre>
      </div>

      {/* MCP Tools Catalog */}
      <div className="bg-white border border-slate-200 rounded p-5 space-y-4">
        <h2 className="text-xs font-semibold text-slate-900">Registered MCP Semantic Tools (Protocol: 2024-11-05)</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {MCP_TOOLS.map((tool) => (
            <div key={tool.name} className="p-4 border border-slate-200 rounded bg-slate-50/50 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold text-slate-900 flex items-center space-x-1.5">
                  <Terminal className="w-3.5 h-3.5 text-slate-400" />
                  <span>{tool.name}</span>
                </span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                  READ_ONLY
                </span>
              </div>

              <p className="text-xs text-slate-600">{tool.description}</p>

              <div className="pt-2 border-t border-slate-200/60 text-[11px] font-mono text-slate-400">
                Input: {tool.parameters}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

