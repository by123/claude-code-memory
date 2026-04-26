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
}

export interface TurnsResponse {
  items: Turn[];
  total: number;
  mode: SearchMode;
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
