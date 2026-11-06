"use client";

import { useEffect, useState } from "react";
import { Search, Filter, Layers, FileText, User } from "lucide-react";
import { api } from "@/lib/api/client";
import { Asset } from "@/lib/types/api";

const ASSET_TYPES = [
  "ALL",
  "TABLE",
  "TRANSFORMATION_MODEL",
  "DASHBOARD",
  "METRIC",
  "DOCUMENTATION",
  "SLACK_CHANNEL",
  "GITHUB_PR",
];

export default function CatalogPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedType, setSelectedType] = useState("ALL");
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadAssets();
  }, [selectedType]);

  async function loadAssets() {
    setLoading(true);
    try {
      const typeParam = selectedType === "ALL" ? undefined : selectedType;
      const data = await api.getAssets({ query: searchTerm, type: typeParam });
      setAssets(data);
      if (data.length > 0 && !selectedAsset) {
        setSelectedAsset(data[0]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    loadAssets();
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between pb-2 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Metadata Catalog</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Discover tables, transformation models, metrics, dashboards, and certified business terms.
          </p>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex items-center justify-between gap-4">
        <form onSubmit={handleSearchSubmit} className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by asset name, qualified identifier, or description..."
            className="w-full pl-9 pr-4 py-2 border border-slate-200 rounded text-xs focus:outline-none focus:border-slate-400 text-slate-900 bg-white"
          />
        </form>

        <div className="flex space-x-1.5">
          {ASSET_TYPES.map((t) => (
            <button
              key={t}
              onClick={() => setSelectedType(t)}
              className={`px-2.5 py-1.5 text-[11px] rounded font-medium transition-colors ${
                selectedType === t
                  ? "bg-slate-900 text-white"
                  : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {t.replace("_", " ")}
            </button>
          ))}
        </div>
      </div>

      {/* Two Column Layout: Asset List & Details Inspector */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
        {/* Left: Assets List */}
        <div className="md:col-span-5 bg-white border border-slate-200 rounded divide-y divide-slate-100 max-h-[680px] overflow-y-auto">
          {loading ? (
            <div className="p-8 text-center text-xs text-slate-400">Loading catalog assets...</div>
          ) : assets.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400">No assets match criteria.</div>
          ) : (
            assets.map((ast) => (
              <div
                key={ast.id}
                onClick={() => setSelectedAsset(ast)}
                className={`p-3.5 cursor-pointer transition-colors ${
                  selectedAsset?.id === ast.id ? "bg-slate-100/70" : "hover:bg-slate-50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-900 truncate max-w-[200px]">
                    {ast.name}
                  </span>
                  <span
                    className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-medium ${
                      ast.certification_status === "CERTIFIED"
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : "bg-amber-50 text-amber-700 border border-amber-200"
                    }`}
                  >
                    {ast.certification_status}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 font-mono mt-0.5 truncate">
                  {ast.qualified_name}
                </div>
                <div className="flex items-center justify-between text-[11px] text-slate-500 mt-2">
                  <span className="text-[10px] uppercase tracking-wider font-semibold text-slate-400">
                    {ast.asset_type.replace("_", " ")}
                  </span>
                  <span>{ast.owner_name || "Unassigned"}</span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Right: Asset Detail Inspector */}
        <div className="md:col-span-7 bg-white border border-slate-200 rounded p-5 space-y-4">
          {selectedAsset ? (
            <>
              <div className="border-b border-slate-100 pb-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-bold text-slate-900">{selectedAsset.name}</h2>
                  <span className="text-xs font-mono text-slate-400">ID: {selectedAsset.id}</span>
                </div>
                <p className="text-xs text-slate-500 font-mono mt-1">{selectedAsset.qualified_name}</p>
              </div>

              <div className="space-y-1.5">
                <h3 className="text-xs font-semibold text-slate-700">Semantic Description</h3>
                <p className="text-xs text-slate-600 leading-relaxed bg-slate-50 p-3 rounded border border-slate-200/60">
                  {selectedAsset.description || "No description cataloged yet."}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="p-3 border border-slate-100 rounded bg-slate-50/50">
                  <span className="text-slate-400 text-[11px] block">Verified Owner</span>
                  <span className="font-medium text-slate-800 mt-0.5 block flex items-center space-x-1">
                    <User className="w-3.5 h-3.5 text-slate-400" />
                    <span>{selectedAsset.owner_name || "Unassigned"}</span>
                  </span>
                </div>

                <div className="p-3 border border-slate-100 rounded bg-slate-50/50">
                  <span className="text-slate-400 text-[11px] block">Provenance Anchor</span>
                  <span className="font-mono text-[11px] text-slate-700 mt-0.5 block flex items-center space-x-1">
                    <FileText className="w-3.5 h-3.5 text-slate-400" />
                    <span>{selectedAsset.provenance_id || "Direct Ingestion"}</span>
                  </span>
                </div>
              </div>

              {selectedAsset.columns && selectedAsset.columns.length > 0 && (
                <div className="space-y-2 pt-2">
                  <h3 className="text-xs font-semibold text-slate-700">
                    Schema Attributes ({selectedAsset.columns.length})
                  </h3>
                  <div className="border border-slate-200 rounded divide-y divide-slate-100 max-h-[220px] overflow-y-auto">
                    {selectedAsset.columns.map((c) => (
                      <div key={c.name} className="px-3 py-2 flex items-center justify-between text-xs">
                        <span className="font-mono text-slate-800">
                          {c.name} {c.is_primary_key && <span className="text-amber-600 text-[10px] ml-1">[PK]</span>}
                        </span>
                        <span className="text-[11px] text-slate-400 font-mono">{c.data_type}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="p-12 text-center text-xs text-slate-400">Select an asset to inspect details.</div>
          )}
        </div>
      </div>
    </div>
  );
}

