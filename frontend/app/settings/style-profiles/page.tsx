"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Loader2, Plus, Sparkles, Trash2, AlertCircle, Pencil } from "lucide-react";
import {
  type AnalyzeResult,
  type StyleProfile,
  analyzeStyle,
  createStyleProfile,
  deleteStyleProfile,
  listStyleProfiles,
  renameStyleProfile,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type StyleData = {
  display_name?: string;
  dominant_language?: string;
  language_mixing?: string;
  formality_level?: string;
  warmth_level?: string;
  directness_level?: string;
  humor_style?: string;
  emoji_usage?: string;
  average_reply_length?: string;
  greeting_style?: string;
  closing_style?: string;
  conflict_style?: string;
  support_style?: string;
  decision_making_style?: string;
  common_phrases?: string[];
  do_not_copy?: string[];
  compact_directive?: string;
};

export default function StyleProfilesPage() {
  const [profiles, setProfiles] = useState<StyleProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  async function load() {
    try {
      const data = await listStyleProfiles();
      setProfiles(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <main className="min-h-dvh">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-5 sm:py-8 fade-up">
        <Link
          href="/settings"
          className="inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg mb-6 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Settings
        </Link>

        <div className="flex items-start justify-between mb-2 gap-3">
          <h1 className="text-2xl sm:text-3xl font-semibold text-fg tracking-tighter">
            Conversation Style Profiles
          </h1>
          {!showForm && (
            <button
              onClick={() => setShowForm(true)}
              className="inline-flex items-center gap-1.5 rounded-xl bg-accent text-on-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover transition-all active:scale-[0.98] shadow-md shadow-accent/25 shrink-0"
            >
              <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
              New
            </button>
          )}
        </div>
        <p className="text-sm sm:text-base text-fg-muted mb-6">
          Teach the assistant to adopt a communication style — tone, rhythm, length —
          based on a sample chat. Style adaptation only; the assistant never
          claims to be that person.
        </p>

        {showForm && (
          <CreateForm
            onCancel={() => setShowForm(false)}
            onCreated={(p) => {
              setProfiles((prev) => [p, ...prev]);
              setShowForm(false);
            }}
          />
        )}

        {error && (
          <div className="glass rounded-xl p-3 mb-4 flex items-start gap-2 text-sm text-danger">
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <p className="text-sm text-fg-muted">Loading…</p>
        ) : profiles.length === 0 && !showForm ? (
          <div className="text-center py-12 glass rounded-2xl">
            <Sparkles className="h-6 w-6 text-fg-subtle mx-auto mb-2 opacity-60" />
            <p className="text-sm text-fg-muted">No style profiles yet.</p>
            <p className="text-xs text-fg-subtle mt-1">
              Tap <span className="text-fg-muted">New</span> to create your first.
            </p>
          </div>
        ) : (
          <ul className="space-y-2">
            {profiles.map((p) => (
              <ProfileCard
                key={p.id}
                profile={p}
                onRenamed={(updated) =>
                  setProfiles((prev) =>
                    prev.map((x) => (x.id === updated.id ? updated : x)),
                  )
                }
                onDeleted={(id) =>
                  setProfiles((prev) => prev.filter((x) => x.id !== id))
                }
              />
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}

// =============================================================================
// Profile card with rename + delete
// =============================================================================

function ProfileCard({
  profile,
  onRenamed,
  onDeleted,
}: {
  profile: StyleProfile;
  onRenamed: (p: StyleProfile) => void;
  onDeleted: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(profile.profile_name);
  const [expanded, setExpanded] = useState(false);
  const style = profile.extracted_style as StyleData;

  async function save() {
    const t = draft.trim();
    if (!t || t === profile.profile_name) {
      setEditing(false);
      return;
    }
    try {
      const updated = await renameStyleProfile(profile.id, t);
      onRenamed(updated);
    } catch (e) {
      alert(String(e));
    } finally {
      setEditing(false);
    }
  }

  async function handleDelete() {
    if (!confirm(`Delete "${profile.profile_name}"?`)) return;
    try {
      await deleteStyleProfile(profile.id);
      onDeleted(profile.id);
    } catch (e) {
      alert(String(e));
    }
  }

  return (
    <li className="glass rounded-xl p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          {editing ? (
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={save}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  save();
                } else if (e.key === "Escape") {
                  setDraft(profile.profile_name);
                  setEditing(false);
                }
              }}
              className="w-full bg-transparent text-sm font-medium text-fg outline-none border-b border-accent/40"
            />
          ) : (
            <p className="text-sm font-medium text-fg">{profile.profile_name}</p>
          )}
          <p className="text-xs text-fg-muted mt-1">
            {profile.source_type} · {profile.sample_count} messages analyzed
          </p>
          {style.compact_directive && (
            <p className="text-xs text-fg-soft mt-2 leading-relaxed">
              {style.compact_directive}
            </p>
          )}
          {expanded && <ProfileDetails style={style} />}
          <button
            onClick={() => setExpanded((v) => !v)}
            className="mt-2 text-xs text-accent hover:underline"
          >
            {expanded ? "Hide details" : "Show full profile"}
          </button>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <button
            onClick={() => setEditing(true)}
            className="h-7 w-7 grid place-items-center text-fg-subtle hover:text-fg"
            aria-label="Rename"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={handleDelete}
            className="h-7 w-7 grid place-items-center text-fg-subtle hover:text-danger"
            aria-label="Delete"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </li>
  );
}

function ProfileDetails({ style }: { style: StyleData }) {
  const rows: [string, string | undefined | string[]][] = [
    ["Language", style.dominant_language],
    ["Mixing", style.language_mixing],
    ["Formality", style.formality_level],
    ["Warmth", style.warmth_level],
    ["Directness", style.directness_level],
    ["Humor", style.humor_style],
    ["Emoji use", style.emoji_usage],
    ["Reply length", style.average_reply_length],
    ["Greeting", style.greeting_style],
    ["Closing", style.closing_style],
    ["Conflict", style.conflict_style],
    ["Support", style.support_style],
    ["Decisions", style.decision_making_style],
    ["Common phrases", style.common_phrases],
    ["Do not copy", style.do_not_copy],
  ];
  return (
    <dl className="mt-3 space-y-1 text-xs">
      {rows.map(([k, v]) =>
        v && (Array.isArray(v) ? v.length > 0 : true) ? (
          <div key={k} className="flex gap-2">
            <dt className="text-fg-muted w-28 shrink-0">{k}</dt>
            <dd className="text-fg-soft flex-1">
              {Array.isArray(v) ? v.join(", ") : v}
            </dd>
          </div>
        ) : null,
      )}
    </dl>
  );
}

// =============================================================================
// Create form: paste → analyze → preview → save
// =============================================================================

function CreateForm({
  onCancel,
  onCreated,
}: {
  onCancel: () => void;
  onCreated: (p: StyleProfile) => void;
}) {
  const [transcript, setTranscript] = useState("");
  const [targetName, setTargetName] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [profileName, setProfileName] = useState("");

  async function handleAnalyze() {
    setError(null);
    if (transcript.trim().length < 20) {
      setError("Paste at least a few messages.");
      return;
    }
    setAnalyzing(true);
    try {
      const res = await analyzeStyle(transcript, targetName || undefined);
      setResult(res);
      setProfileName(res.suggested_name);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleSave() {
    if (!result) return;
    if (!profileName.trim()) {
      setError("Give the profile a name.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const created = await createStyleProfile({
        profile_name: profileName.trim(),
        source_type: result.source_type,
        extracted_style: result.profile,
        sample_count: result.sample_count,
      });
      onCreated(created);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  // ---------- Preview state ----------
  if (result) {
    const style = result.profile as StyleData;
    return (
      <div className="glass rounded-2xl p-5 mb-6 fade-up">
        <h2 className="text-sm font-medium text-fg mb-3">Preview</h2>

        <label className="block mb-4">
          <span className="text-xs font-medium text-fg-muted">Profile name</span>
          <input
            type="text"
            value={profileName}
            onChange={(e) => setProfileName(e.target.value)}
            placeholder={result.suggested_name || "Profile name"}
            className={inputCls}
          />
        </label>

        {style.compact_directive && (
          <div className="mb-3">
            <p className="text-xs font-medium text-fg-muted mb-1">Style summary</p>
            <p className="text-sm text-fg-soft leading-relaxed">
              {style.compact_directive}
            </p>
          </div>
        )}

        <div className="mb-3 grid grid-cols-2 gap-y-1 gap-x-3 text-xs">
          <Item label="Language" v={style.dominant_language} />
          <Item label="Formality" v={style.formality_level} />
          <Item label="Warmth" v={style.warmth_level} />
          <Item label="Directness" v={style.directness_level} />
          <Item label="Emoji" v={style.emoji_usage} />
          <Item label="Length" v={style.average_reply_length} />
        </div>

        {style.do_not_copy && style.do_not_copy.length > 0 && (
          <div className="mb-3 p-2.5 rounded-lg bg-danger-soft border border-danger/20">
            <p className="text-xs font-medium text-danger mb-1">
              Will NEVER be reproduced
            </p>
            <ul className="text-xs text-fg-soft space-y-0.5">
              {style.do_not_copy.slice(0, 6).map((x, i) => (
                <li key={i}>· {x}</li>
              ))}
            </ul>
          </div>
        )}

        <p className="text-[11px] text-fg-subtle mb-4">
          {result.sample_count} target messages · format: {result.source_type}
        </p>

        {error && <p className="text-sm text-danger mb-3">{error}</p>}

        <div className="flex justify-end gap-2 pt-2 border-t border-border">
          <button
            type="button"
            onClick={() => setResult(null)}
            className="px-3 py-1.5 rounded-lg text-sm text-fg-muted hover:bg-fg/5"
          >
            Re-analyze
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 rounded-lg text-sm text-fg-muted hover:bg-fg/5"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !profileName.trim()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent text-on-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-50 transition-all"
          >
            {saving ? "Saving…" : "Save profile"}
          </button>
        </div>
      </div>
    );
  }

  // ---------- Input state ----------
  return (
    <div className="glass rounded-2xl p-5 mb-6 fade-up">
      <p className="text-xs text-fg-muted mb-3">
        Paste a WhatsApp/Telegram export or any chat transcript. The text is
        used to extract a style profile, then discarded — not stored.
      </p>

      <label className="block mb-3">
        <span className="text-xs font-medium text-fg-muted">
          Target name (optional)
        </span>
        <input
          type="text"
          value={targetName}
          onChange={(e) => setTargetName(e.target.value)}
          placeholder="Whose style? — leave blank to auto-detect"
          className={inputCls}
        />
      </label>

      <label className="block mb-4">
        <span className="text-xs font-medium text-fg-muted">Chat transcript</span>
        <textarea
          rows={10}
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          placeholder={`Examples that work well:\n\n[9/5/24, 10:23 PM] Anna: hey beb...\n[9/5/24, 10:24 PM] Anna: udah makan?\n\nOr Telegram text export, or any paste with multiple messages from the target.`}
          className={cn(inputCls, "resize-none font-mono text-[12px]")}
        />
      </label>

      {error && <p className="text-sm text-danger mb-3">{error}</p>}

      <div className="flex justify-end gap-2 pt-2 border-t border-border">
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 rounded-lg text-sm text-fg-muted hover:bg-fg/5"
        >
          Cancel
        </button>
        <button
          onClick={handleAnalyze}
          disabled={analyzing || transcript.trim().length < 20}
          className="inline-flex items-center gap-1.5 rounded-lg bg-accent text-on-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-50 transition-all"
        >
          {analyzing ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Analyzing…
            </>
          ) : (
            "Analyze style"
          )}
        </button>
      </div>
    </div>
  );
}

function Item({ label, v }: { label: string; v: string | undefined }) {
  if (!v) return null;
  return (
    <div>
      <span className="text-fg-muted">{label}:</span>{" "}
      <span className="text-fg-soft">{v}</span>
    </div>
  );
}

const inputCls =
  "mt-1.5 w-full rounded-xl border border-border-strong bg-bg/40 backdrop-blur-sm px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all";
