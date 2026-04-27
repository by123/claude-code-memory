export type Scope = "project" | "global";
export type SearchMode = "keyword" | "semantic";

export interface Turn {
  id: string;
  session_id: string;
  ts: number;
  cwd?: string | null;
  user_msg: string;
  assistant_msg: string;
  tags: string[];
  score?: number | null;
  retrieval_count?: number;
}

export interface RetrievalSummary {
  id: string;
  ts: number;
  session_id: string | null;
  cwd: string | null;
  prompt: string;
  scope_used: string | null;
  hit_count: number;
}

export interface RetrievalHit {
  turn_id: string;
  scope: string | null;
  kind: string | null;
  score: number;
  rank: number;
  turn: Turn | null;
}

export interface RetrievalDetail extends RetrievalSummary {
  hits: RetrievalHit[];
}

export interface RetrievalsResponse {
  items: RetrievalSummary[];
  total: number;
}

export interface TurnRetrievalsResponse {
  items: Array<RetrievalSummary & { score: number; rank: number }>;
  total: number;
}

export interface TurnsResponse {
  items: Turn[];
  total: number;
  mode: SearchMode;
}

export interface TopReferencedResponse {
  items: Turn[];
}

export interface ScopesResponse {
  project: boolean;
  global: boolean;
  project_dir: string | null;
  global_dir: string;
  cwd: string;
}

export interface TagInfo {
  name: string;
  count: number;
  created_at?: number;
}
