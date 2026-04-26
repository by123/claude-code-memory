import type { Scope, SearchMode, ScopesResponse, TagInfo, TurnsResponse } from "./types";

async function jsonFetch<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const res = await fetch(input, init);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${text}`);
  }
  return (await res.json()) as T;
}

export const api = {
  scopes: () => jsonFetch<ScopesResponse>("/api/scopes"),

  turns: (params: {
    scope: Scope;
    page?: number;
    pageSize?: number;
    q?: string;
    tag?: string;
    mode?: SearchMode;
  }) => {
    const sp = new URLSearchParams();
    sp.set("scope", params.scope);
    if (params.page) sp.set("page", String(params.page));
    if (params.pageSize) sp.set("page_size", String(params.pageSize));
    if (params.q) sp.set("q", params.q);
    if (params.tag) sp.set("tag", params.tag);
    if (params.mode) sp.set("mode", params.mode);
    return jsonFetch<TurnsResponse>(`/api/turns?${sp}`);
  },

  deleteTurn: (scope: Scope, id: string) =>
    jsonFetch<{ ok: true }>(`/api/turns/${scope}/${id}`, { method: "DELETE" }),

  addTag: (scope: Scope, id: string, name: string) =>
    jsonFetch<{ ok: true }>(`/api/turns/${scope}/${id}/tags`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),

  removeTag: (scope: Scope, id: string, name: string) =>
    jsonFetch<{ ok: true }>(`/api/turns/${scope}/${id}/tags/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),

  tags: (scope: Scope) => jsonFetch<TagInfo[]>(`/api/tags?scope=${scope}`),
};
