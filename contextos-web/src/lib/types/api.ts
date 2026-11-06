export interface Source {
  id: string;
  name: string;
  source_type: string;
  connection_config: Record<string, any>;
  is_active: boolean;
  freshness_threshold_seconds?: number;
  auth_type?: string;
  oauth_scopes?: string[];
  last_sync_at?: string;
  last_sync_status?: string;
  created_at: string;
}

export interface SyncCheckpoint {
  id: string;
  source_id: string;
  cursor_value: string;
  checkpoint_metadata: Record<string, any>;
  updated_at: string;
}

export interface DeadLetterRecord {
  id: string;
  source_id: string;
  raw_record_id: string;
  payload: Record<string, any>;
  error_reason: string;
  retry_count: number;
  failed_at: string;
}

export interface SyncJob {
  sync_id: string;
  source_id: string;
  status: string;
  entities_extracted: number;
  relationships_extracted: number;
  error_message?: string;
  started_at: string;
  completed_at?: string;
}

export interface Column {
  name: string;
  data_type: string;
  is_primary_key: boolean;
  is_nullable: boolean;
  description?: string;
}

export interface Asset {
  id: string;
  source_id: string;
  external_id: string;
  name: string;
  qualified_name: string;
  asset_type: string;
  description?: string;
  certification_status: "UNVERIFIED" | "PENDING_REVIEW" | "CERTIFIED" | "DEPRECATED" | "DISPUTED";
  owner_name?: string;
  columns?: Column[];
  tags?: string[];
  provenance_id?: string;
  created_at: string;
}

export interface LineageGraph {
  root_asset_id: string;
  depth: number;
  direction: string;
  nodes: Array<{
    id: string;
    name: string;
    qualified_name: string;
    asset_type: string;
    certification_status: string;
    owner_name?: string;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    type?: string;
    relationship_type?: string;
    confidence: number;
  }>;
}

export interface MatchedEntity {
  asset_id: string;
  name: string;
  qualified_name: string;
  asset_type: string;
  relevance_score: number;
  certification_status: string;
  owner_name?: string;
  description?: string;
  provenance?: {
    source_id: string;
    extraction_method: string;
    source_hash: string;
    evidence_snippet: Record<string, any>;
  };
}

export interface DiscrepancyReport {
  discrepancy_type: string;
  description: string;
  confidence: number;
  evidence_asset_ids: string[];
}

export interface AISummary {
  headline: string;
  root_cause_analysis: string;
  evidence_trail: string[];
  suggested_remediation: string;
  confidence_score: number;
  grounded_model: string;
}

export interface ContextResponse {
  query: string;
  matched_entities: MatchedEntity[];
  lineage_subgraph: {
    nodes: Array<any>;
    edges: Array<any>;
  };
  discrepancies: DiscrepancyReport[];
  freshness_warning?: string;
  ai_summary?: AISummary;
  trace_id: string;
}

export interface ApprovalItem {
  request_id: string;
  suggestion_id: string;
  asset_id: string;
  asset_name: string;
  asset_type: string;
  action_type: string;
  suggestion_type: string;
  proposed_value: Record<string, any>;
  reasoning: string;
  confidence: number;
  requested_by: string;
  status: string;
  requested_at: string;
}

export interface TraceSpan {
  id: string;
  parent_span_id?: string;
  span_type: string;
  name: string;
  input_payload: Record<string, any>;
  output_payload: Record<string, any>;
  latency_ms: number;
  status: string;
  started_at: string;
  ended_at?: string;
}

export interface AgentRun {
  id?: string;
  run_id: string;
  agent_id: string;
  trigger_event: string;
  input_prompt: string;
  status: string;
  latency_ms: number;
  total_tokens: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  estimated_cost_usd: number;
  output_response?: string;
  retrieved_context_ids: string[];
  error_message?: string;
  started_at: string;
  completed_at?: string;
  spans?: TraceSpan[];
}

export interface EvaluationRun {
  id: string;
  dataset_id: string;
  dataset_version: string;
  model_version: string;
  overall_recall_at_k: number;
  overall_entity_resolution_accuracy: number;
  overall_context_relevance: number;
  policy_compliance_rate: number;
  average_latency_ms: number;
  total_cost_usd: number;
  results_count: number;
  executed_at: string;
}
