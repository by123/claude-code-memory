import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { ScopesResponse, SearchMode, Scope, TagInfo, Turn } from "./types";
import { TurnCard } from "./components/TurnCard";
import { RetrievalsView } from "./components/RetrievalsView";

const PAGE_SIZE = 15;

type View = "turns" | "retrievals";

export default function App() {
  const [scopes, setScopes] = useState<ScopesResponse | null>(null);
  const [scope, setScope] = useState<Scope>("global");
  const [view, setView] = useState<View>("turns");
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("keyword");
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [items, setItems] = useState<Turn[]>([]);
  const [total, setTotal] = useState(0);
  const [tags, setTags] = useState<TagInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    const stored = typeof localStorage !== "undefined" ? localStorage.getItem("cm-theme") : null;
    if (stored === "light" || stored === "dark") return stored;
    if (typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: light)").matches) {
      return "light";
    }
    return "dark";
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("cm-theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  useEffect(() => {
    api.scopes().then((s) => {
      setScopes(s);
      if (s.project && s.project_turn_count > 0) setScope("project");
      else setScope("global");
    });
  }, []);

  const refreshTags = (s: Scope) => {
    api.tags(s).then(setTags).catch(() => setTags([]));
  };

  useEffect(() => {
    if (!scopes) return;
    refreshTags(scope);
  }, [scope, scopes]);

  useEffect(() => {
    if (view !== "turns") return;
    if (!scopes) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .turns({
        scope,
        page,
        pageSize: PAGE_SIZE,
        q: submittedQuery || undefined,
        tag: activeTag || undefined,
        mode,
      })
      .then((r) => {
        if (cancelled) return;
        setItems(r.items);
        setTotal(r.total);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(String(e));
        setItems([]);
        setTotal(0);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [scopes, scope, page, submittedQuery, activeTag, mode, view]);

  const totalPages = useMemo(() => {
    if (mode === "semantic") return 1;
    return Math.max(1, Math.ceil(total / PAGE_SIZE));
  }, [total, mode]);

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setSubmittedQuery(query.trim());
  };

  const onClear = () => {
    setQuery("");
    setSubmittedQuery("");
    setActiveTag(null);
    setPage(1);
  };

  const handleDelete = async (turn: Turn) => {
    if (!confirm("Delete this turn permanently?")) return;
    try {
      await api.deleteTurn(scope, turn.id);
      setItems((prev) => prev.filter((t) => t.id !== turn.id));
      setTotal((n) => Math.max(0, n - 1));
      refreshTags(scope);
    } catch (e) {
      alert(`Delete failed: ${e}`);
    }
  };

  const handleAddTag = async (turn: Turn, name: string) => {
    const clean = name.trim().replace(/^#/, "");
    if (!clean) return;
    try {
      await api.addTag(scope, turn.id, clean, "custom");
      setItems((prev) =>
        prev.map((t) =>
          t.id === turn.id && !t.tags.some((tag) => tag.name === clean)
            ? {
                ...t,
                tags: [...t.tags, { name: clean, kind: "custom", source: "manual" }].sort(
                  (a, b) => `${a.kind}:${a.name}`.localeCompare(`${b.kind}:${b.name}`),
                ),
              }
            : t,
        ),
      );
      refreshTags(scope);
    } catch (e) {
      alert(`Add tag failed: ${e}`);
    }
  };

  const handleRemoveTag = async (turn: Turn, name: string) => {
    try {
      await api.removeTag(scope, turn.id, name);
      setItems((prev) =>
        prev.map((t) =>
          t.id === turn.id ? { ...t, tags: t.tags.filter((x) => x.name !== name) } : t,
        ),
      );
      refreshTags(scope);
    } catch (e) {
      alert(`Remove tag failed: ${e}`);
    }
  };

  const projectPath = scopes?.project_dir ?? "no project marker found";
  const globalPath = scopes?.global_dir ?? "";

  return (
    <div className="layout">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" />
          <span className="brand-name">lynx-memory</span>
          <span className="brand-sub">history</span>
        </div>

        <div className="scope-switch" role="tablist" aria-label="scope">
          <button
            className={`scope-btn${scope === "project" ? " active" : ""}`}
            disabled={!scopes?.project}
            onClick={() => {
              setScope("project");
              setPage(1);
            }}
            data-tooltip={projectPath}
          >
            <span className="scope-dot" /> Project
          </button>
          <button
            className={`scope-btn${scope === "global" ? " active" : ""}`}
            onClick={() => {
              setScope("global");
              setPage(1);
            }}
            data-tooltip={globalPath}
          >
            <span className="scope-dot" /> Global
          </button>
        </div>

        <button
          className="theme-toggle"
          onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
          title={theme === "dark" ? "switch to light mode" : "switch to dark mode"}
          aria-label="toggle theme"
        >
          {theme === "dark" ? "☀" : "☾"}
        </button>
      </header>

      <nav className="view-tabs" role="tablist" aria-label="view">
        <button
          role="tab"
          className={view === "turns" ? "view-tab active" : "view-tab"}
          onClick={() => setView("turns")}
        >
          Turns
        </button>
        <button
          role="tab"
          className={view === "retrievals" ? "view-tab active" : "view-tab"}
          onClick={() => setView("retrievals")}
          title="每次对话命中的历史记录"
        >
          Retrievals
        </button>
      </nav>

      <div className="main">
        {view === "turns" && (
        <aside className="sidebar">
          <form className="search" onSubmit={onSearch}>
            <input
              placeholder="Search…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <div className="mode">
              <label className={mode === "keyword" ? "active" : ""}>
                <input
                  type="radio"
                  checked={mode === "keyword"}
                  onChange={() => setMode("keyword")}
                />
                keyword
              </label>
              <label className={mode === "semantic" ? "active" : ""}>
                <input
                  type="radio"
                  checked={mode === "semantic"}
                  onChange={() => setMode("semantic")}
                />
                semantic
              </label>
            </div>
            <div className="search-actions">
              <button type="submit">Search</button>
              <button type="button" onClick={onClear}>
                Clear
              </button>
            </div>
          </form>

          <div className="tags-block">
            <div className="block-title">Tags</div>
            {tags.length === 0 ? (
              <div className="empty">no tags yet</div>
            ) : (
              <ul className="tag-list">
                {tags.map((t) => (
                  <li key={t.name}>
                    <button
                      className={activeTag === t.name ? "tag-pill active" : "tag-pill"}
                      onClick={() => {
                        setActiveTag((prev) => (prev === t.name ? null : t.name));
                        setPage(1);
                      }}
                    >
                      [{t.kind}] {t.name} <span className="count">{t.count}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
        )}

        {view === "retrievals" ? (
          <RetrievalsView scope={scope} scopesReady={scopes !== null} />
        ) : (
            <section className="content">
              <div className="status">
                <span>
                  {mode === "semantic" && submittedQuery
                    ? `top ${items.length} semantic matches`
                    : `${total} turn${total === 1 ? "" : "s"}`}
                  {activeTag ? ` · #${activeTag}` : ""}
                  {submittedQuery ? ` · "${submittedQuery}"` : ""}
                </span>
                {loading && <span className="loading">loading…</span>}
              </div>

              {error && <div className="error">{error}</div>}

              <ul className="turns">
                {items.map((t) => (
                  <TurnCard
                    key={t.id}
                    turn={t}
                    scope={scope}
                    onDelete={() => handleDelete(t)}
                    onAddTag={(name) => handleAddTag(t, name)}
                    onRemoveTag={(name) => handleRemoveTag(t, name)}
                  />
                ))}
              </ul>

              {!loading && items.length === 0 && <div className="empty">no turns to show.</div>}

              {mode === "keyword" && totalPages > 1 && (
                <div className="pagination">
                  <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                    ← prev
                  </button>
                  <span>
                    {page} / {totalPages}
                  </span>
                  <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                    next →
                  </button>
                </div>
              )}
            </section>
          )}
      </div>
    </div>
  );
}
