import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { AppSettings } from "../types";

const ANTHROPIC_MODELS = [
  // Latest generation — recommended for summarization
  { value: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5  ★ fast · low cost" },
  { value: "claude-sonnet-4-6",         label: "Claude Sonnet 4.6" },
  { value: "claude-opus-4-7",           label: "Claude Opus 4.7  · premium" },
];

const OPENAI_MODELS = [
  // GPT-5.x series (Responses API)
  { value: "gpt-5.4-nano",  label: "GPT-5.4 nano  ★ fast · low cost" },
  { value: "gpt-5.4-mini",  label: "GPT-5.4 mini" },
  { value: "gpt-5.4",       label: "GPT-5.4  · premium" },
  // GPT-4.1 series
  { value: "gpt-4.1-nano",  label: "GPT-4.1 nano  · low cost" },
  { value: "gpt-4.1-mini",  label: "GPT-4.1 mini" },
  { value: "gpt-4.1",       label: "GPT-4.1" },
  // GPT-4o series
  { value: "gpt-4o-mini",   label: "GPT-4o mini" },
  { value: "gpt-4o",        label: "GPT-4o" },
  // Reasoning models
  { value: "o4-mini",       label: "o4-mini  · reasoning" },
  { value: "o3-mini",       label: "o3-mini  · reasoning" },
  { value: "o3",            label: "o3  · reasoning · premium" },
];

const BACKEND_BASE_URLS: Record<string, string> = {
  sdk: "https://api.anthropic.com",
  openai: "https://api.openai.com/v1",
};

const OPENAI_EMBEDDING_MODELS = [
  { value: "text-embedding-3-large", label: "text-embedding-3-large  ★ higher accuracy" },
  { value: "text-embedding-3-small", label: "text-embedding-3-small  · fast · low cost" },
];

const VOYAGE_MODELS = [
  { value: "voyage-3.5",      label: "voyage-3.5  ★ latest · general purpose" },
  { value: "voyage-3.5-lite", label: "voyage-3.5-lite  · fast · low cost" },
  { value: "voyage-3",        label: "voyage-3  · previous generation" },
  { value: "voyage-3-lite",   label: "voyage-3-lite  · lightweight" },
  { value: "voyage-code-3",   label: "voyage-code-3  · optimized for code" },
];

const DEFAULT_SETTINGS: AppSettings = {
  summary_enabled: false,
  top_k: 5,
  min_score: 0.7,
  scope: "auto",
  summary_model: ANTHROPIC_MODELS[0].value,
  summary_backend: "sdk",
  anthropic_api_key_set: false,
  openai_api_key_set: false,
  voyage_api_key_set: false,
  openai_model: "gpt-5.4-nano",
  openai_base_url: "",
  embedding_backend: "voyage",
  openai_embedding_model: "text-embedding-3-large",
  voyage_model: "voyage-3.5",
};

interface Props {
  open: boolean;
  onClose: () => void;
}

function KeyRow({
  label,
  isSet,
  pendingKey,
  onChange,
  onClear,
  placeholder,
}: {
  label: string;
  isSet: boolean;
  pendingKey: string | null;
  onChange: (v: string) => void;
  onClear: () => void;
  placeholder: string;
}) {
  return (
    <div className="settings-row">
      <div className="settings-label">
        <span>{label}</span>
        <span className="settings-hint">
          {pendingKey === ""
            ? <span className="settings-key-status unset">○ will be removed</span>
            : (isSet || (pendingKey !== null && pendingKey.length > 0))
              ? <span className="settings-key-status set">● configured</span>
              : <span className="settings-key-status unset">○ not set</span>}
        </span>
      </div>
      <div className="settings-key-field">
        <input
          className="settings-input settings-input-key"
          type="text"
          value={pendingKey ?? ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          autoComplete="off"
        />
        {isSet && pendingKey === null && (
          <button className="settings-key-clear" onClick={onClear} title="Remove key">✕</button>
        )}
      </div>
    </div>
  );
}

export function SettingsPanel({ open, onClose }: Props) {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [anthropicKey, setAnthropicKey] = useState<string | null>(null);
  const [openaiKey, setOpenaiKey] = useState<string | null>(null);
  const [voyageKey, setVoyageKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    setSaved(false);
    setAnthropicKey(null);
    setOpenaiKey(null);
    setVoyageKey(null);
    api
      .getSettings()
      .then((s) => {
        setSettings(s);
        setAnthropicKey(s.anthropic_api_key_value ?? null);
        setOpenaiKey(s.openai_api_key_value ?? null);
        setVoyageKey(s.voyage_api_key_value ?? null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const payload: AppSettings = {
        ...settings,
        anthropic_api_key: anthropicKey ?? undefined,
        openai_api_key: openaiKey ?? undefined,
        voyage_api_key: voyageKey ?? undefined,
      };
      await api.putSettings(payload);
      setSettings((s) => ({
        ...s,
        anthropic_api_key_set: anthropicKey ? anthropicKey.trim().length > 0 : s.anthropic_api_key_set,
        openai_api_key_set: openaiKey ? openaiKey.trim().length > 0 : s.openai_api_key_set,
        voyage_api_key_set: voyageKey ? voyageKey.trim().length > 0 : s.voyage_api_key_set,
      }));
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const isAnthropicBackend = settings.summary_backend === "sdk";
  const isOpenAIBackend = settings.summary_backend === "openai";

  const keyMissing = settings.summary_enabled && (
    (isAnthropicBackend && !settings.anthropic_api_key_set && !anthropicKey?.trim()) ||
    (isOpenAIBackend && !settings.openai_api_key_set && !openaiKey?.trim())
  );

  if (!open) return null;

  return (
    <div className="settings-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="settings-panel" ref={panelRef} role="dialog" aria-modal="true" aria-label="Settings">
        <div className="settings-header">
          <span className="settings-title">Settings</span>
          <button className="settings-close" onClick={onClose} aria-label="close">✕</button>
        </div>

        {loading ? (
          <div className="settings-loading">Loading…</div>
        ) : (
          <div className="settings-body">

            {/* ── Embeddings ── */}
            <section className="settings-section">
              <div className="settings-section-title">Embeddings</div>

              <div className="settings-row">
                <div className="settings-label">
                  <span>Backend</span>
                  <span className="settings-hint">Embedding provider for semantic search</span>
                </div>
                <select
                  className="settings-select"
                  value={settings.embedding_backend}
                  onChange={(e) => setSettings((s) => ({ ...s, embedding_backend: e.target.value }))}
                >
                  <option value="voyage">Voyage AI</option>
                  <option value="openai">OpenAI</option>
                </select>
              </div>

              {settings.embedding_backend === "voyage" && (
                <>
                  <div className="settings-row">
                    <div className="settings-label">
                      <span>Voyage model</span>
                    </div>
                    <select
                      className="settings-select"
                      value={settings.voyage_model}
                      onChange={(e) => setSettings((s) => ({ ...s, voyage_model: e.target.value }))}
                    >
                      {VOYAGE_MODELS.map((m) => (
                        <option key={m.value} value={m.value}>{m.label}</option>
                      ))}
                    </select>
                  </div>
                  <KeyRow
                    label="Voyage API key"
                    isSet={settings.voyage_api_key_set}
                    pendingKey={voyageKey}
                    onChange={setVoyageKey}
                    onClear={() => setVoyageKey("")}
                    placeholder="pa-…"
                  />
                  {!settings.voyage_api_key_set && voyageKey === null && (
                    <div className="settings-warning">
                      ⚠ Voyage API key is required for semantic search and memory injection.
                    </div>
                  )}
                </>
              )}

              {settings.embedding_backend === "openai" && (
                <>
                  <div className="settings-row">
                    <div className="settings-label">
                      <span>OpenAI embedding model</span>
                    </div>
                    <select
                      className="settings-select"
                      value={settings.openai_embedding_model}
                      onChange={(e) => setSettings((s) => ({ ...s, openai_embedding_model: e.target.value }))}
                    >
                      {OPENAI_EMBEDDING_MODELS.map((m) => (
                        <option key={m.value} value={m.value}>{m.label}</option>
                      ))}
                    </select>
                  </div>
                  <KeyRow
                    label="OpenAI API key"
                    isSet={settings.openai_api_key_set}
                    pendingKey={openaiKey}
                    onChange={setOpenaiKey}
                    onClear={() => setOpenaiKey("")}
                    placeholder="sk-…"
                  />
                  {!settings.openai_api_key_set && openaiKey === null && (
                    <div className="settings-warning">
                      ⚠ OpenAI API key is required for embedding.
                    </div>
                  )}
                </>
              )}
            </section>

            {/* ── Memory Injection ── */}
            <section className="settings-section">
              <div className="settings-section-title">Memory Injection</div>

              <div className="settings-row">
                <div className="settings-label">
                  <span>Top-K results</span>
                  <span className="settings-hint">Memories injected per prompt</span>
                </div>
                <div className="settings-control">
                  <input
                    type="range" min={1} max={20} step={1}
                    value={settings.top_k}
                    onChange={(e) => setSettings((s) => ({ ...s, top_k: Number(e.target.value) }))}
                  />
                  <span className="settings-value">{settings.top_k}</span>
                </div>
              </div>

              <div className="settings-row">
                <div className="settings-label">
                  <span>Min score</span>
                  <span className="settings-hint">Minimum similarity threshold (0–1)</span>
                </div>
                <div className="settings-control">
                  <input
                    type="range" min={0} max={1} step={0.05}
                    value={settings.min_score}
                    onChange={(e) => setSettings((s) => ({ ...s, min_score: Number(e.target.value) }))}
                  />
                  <span className="settings-value">{settings.min_score.toFixed(2)}</span>
                </div>
              </div>

              <div className="settings-row">
                <div className="settings-label">
                  <span>Retrieval scope</span>
                  <span className="settings-hint">Which memory store to search</span>
                </div>
                <select
                  className="settings-select"
                  value={settings.scope}
                  onChange={(e) => setSettings((s) => ({ ...s, scope: e.target.value }))}
                >
                  <option value="auto">auto (project → global)</option>
                  <option value="global">global only</option>
                  <option value="project">project only</option>
                </select>
              </div>
            </section>

            {/* ── Summarization ── */}
            <section className="settings-section">
              <div className="settings-section-title">Summarization</div>

              <div className="settings-row">
                <div className="settings-label">
                  <span>Enable summarization</span>
                  <span className="settings-hint">Generate a compact summary after each turn</span>
                </div>
                <button
                  className={`settings-toggle${settings.summary_enabled ? " on" : ""}`}
                  onClick={() => setSettings((s) => ({ ...s, summary_enabled: !s.summary_enabled }))}
                  aria-pressed={settings.summary_enabled}
                >
                  <span className="settings-toggle-knob" />
                </button>
              </div>

              <div className="settings-row">
                <div className="settings-label">
                  <span>Backend</span>
                  <span className="settings-hint">API provider for summarization</span>
                </div>
                <select
                  className="settings-select"
                  value={settings.summary_backend}
                  onChange={(e) => setSettings((s) => ({ ...s, summary_backend: e.target.value }))}
                  disabled={!settings.summary_enabled}
                >
                  <option value="sdk">Anthropic</option>
                  <option value="openai">OpenAI</option>
                </select>
              </div>

              {/* Anthropic branch */}
              {isAnthropicBackend && (
                <>
                  <div className="settings-row">
                    <div className="settings-label">
                      <span>Base URL</span>
                    </div>
                    <span className="settings-static">{BACKEND_BASE_URLS.sdk}</span>
                  </div>
                  <div className="settings-row">
                    <div className="settings-label">
                      <span>Model</span>
                      <span className="settings-hint">Anthropic model used for summarization</span>
                    </div>
                    <select
                      className="settings-select"
                      value={settings.summary_model}
                      onChange={(e) => setSettings((s) => ({ ...s, summary_model: e.target.value }))}
                      disabled={!settings.summary_enabled}
                    >
                      {ANTHROPIC_MODELS.map((m) => (
                        <option key={m.value} value={m.value}>{m.label}</option>
                      ))}
                    </select>
                  </div>
                  <KeyRow
                    label="Anthropic API key"
                    isSet={settings.anthropic_api_key_set}
                    pendingKey={anthropicKey}
                    onChange={setAnthropicKey}
                    onClear={() => setAnthropicKey("")}
                    placeholder="sk-ant-…"
                  />
                </>
              )}

              {/* OpenAI branch */}
              {isOpenAIBackend && (
                <>
                  <div className="settings-row">
                    <div className="settings-label">
                      <span>Model</span>
                      <span className="settings-hint">OpenAI model used for summarization</span>
                    </div>
                    <select
                      className="settings-select"
                      value={settings.openai_model}
                      onChange={(e) => setSettings((s) => ({ ...s, openai_model: e.target.value }))}
                      disabled={!settings.summary_enabled}
                    >
                      {OPENAI_MODELS.map((m) => (
                        <option key={m.value} value={m.value}>{m.label}</option>
                      ))}
                    </select>
                  </div>
                  <div className="settings-row">
                    <div className="settings-label">
                      <span>Base URL</span>
                    </div>
                    <span className="settings-static">{BACKEND_BASE_URLS.openai}</span>
                  </div>
                  <KeyRow
                    label="OpenAI API key"
                    isSet={settings.openai_api_key_set}
                    pendingKey={openaiKey}
                    onChange={setOpenaiKey}
                    onClear={() => setOpenaiKey("")}
                    placeholder="sk-…"
                  />
                </>
              )}

              {keyMissing && (
                <div className="settings-warning">
                  ⚠ No API key configured for the selected backend — summarization will not run.
                </div>
              )}
            </section>

            {error && <div className="settings-error">{error}</div>}

            <div className="settings-footer">
              <button className="settings-cancel" onClick={onClose}>Cancel</button>
              <button
                className={`settings-save${saved ? " saved" : ""}`}
                onClick={handleSave}
                disabled={saving}
              >
                {saved ? "Saved!" : saving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
