"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
  AlertCircle,
  Pencil,
  Upload,
  FileText,
  X,
} from "lucide-react";
import {
  type AnalyzeResult,
  type PreviewParseResult,
  type PreviewSender,
  type StyleProfile,
  analyzeStyle,
  createStyleProfile,
  deleteStyleProfile,
  listStyleProfiles,
  previewParseStyle,
  renameStyleProfile,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const MAX_UPLOAD_CHARS = 5_000_000;
const LARGE_FILE_WARN_THRESHOLD = 200_000;

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
          <CreateWizard
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
// 3-step wizard: Input (paste/upload) → Confirm sender → Analyze + save
// =============================================================================

type Step =
  | { kind: "input" }
  | { kind: "confirm"; preview: PreviewParseResult }
  | { kind: "preview"; result: AnalyzeResult; targetUsed: string };

function CreateWizard({
  onCancel,
  onCreated,
}: {
  onCancel: () => void;
  onCreated: (p: StyleProfile) => void;
}) {
  const [step, setStep] = useState<Step>({ kind: "input" });
  const [transcript, setTranscript] = useState("");
  const [filename, setFilename] = useState<string | null>(null);
  const [loading, setLoading] = useState<"" | "preview" | "analyze" | "save">("");
  const [error, setError] = useState<string | null>(null);
  // Keep the last preview so the user can step back from analyze→confirm
  // without re-running the parse.
  const [lastPreview, setLastPreview] = useState<PreviewParseResult | null>(null);

  // ----- input step actions -----
  async function handlePreview() {
    setError(null);
    if (transcript.length > MAX_UPLOAD_CHARS) {
      setError(
        `Transcript too large (${Math.round(transcript.length / 1024)} KB). Max ${Math.round(MAX_UPLOAD_CHARS / 1024)} KB.`,
      );
      return;
    }
    if (transcript.trim().length < 20) {
      setError("Paste or upload at least a few messages.");
      return;
    }
    setLoading("preview");
    try {
      const preview = await previewParseStyle(transcript);
      setLastPreview(preview);
      setStep({ kind: "confirm", preview });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading("");
    }
  }

  function clearInput() {
    setTranscript("");
    setFilename(null);
    setError(null);
  }

  // ----- confirm step action -----
  async function handleAnalyze(targetName: string | null) {
    setError(null);
    setLoading("analyze");
    try {
      const result = await analyzeStyle(transcript, targetName || undefined);
      setStep({ kind: "preview", result, targetUsed: targetName || "(auto)" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading("");
    }
  }

  // ----- preview step action -----
  async function handleSave(profileName: string) {
    if (step.kind !== "preview") return;
    if (!profileName.trim()) {
      setError("Give the profile a name.");
      return;
    }
    setError(null);
    setLoading("save");
    try {
      const created = await createStyleProfile({
        profile_name: profileName.trim(),
        source_type: step.result.source_type,
        extracted_style: step.result.profile,
        sample_count: step.result.sample_count,
      });
      onCreated(created);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading("");
    }
  }

  return (
    <div className="glass rounded-2xl p-5 mb-6 fade-up">
      <StepIndicator step={step.kind} />

      {step.kind === "input" && (
        <InputStep
          transcript={transcript}
          setTranscript={setTranscript}
          filename={filename}
          setFilename={setFilename}
          onClear={clearInput}
          setError={setError}
        />
      )}

      {step.kind === "confirm" && (
        <ConfirmStep
          preview={step.preview}
          onBack={() => setStep({ kind: "input" })}
          onAnalyze={handleAnalyze}
          loading={loading === "analyze"}
        />
      )}

      {step.kind === "preview" && (
        <PreviewStep
          result={step.result}
          onSave={handleSave}
          loading={loading === "save"}
          onReanalyze={() => {
            if (lastPreview) {
              setStep({ kind: "confirm", preview: lastPreview });
            } else {
              setStep({ kind: "input" });
            }
          }}
        />
      )}

      {error && (
        <div className="mt-3 flex items-start gap-2 text-sm text-danger">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {step.kind === "input" && (
        <div className="flex justify-end gap-2 pt-3 mt-3 border-t border-border">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 rounded-lg text-sm text-fg-muted hover:bg-fg/5"
          >
            Cancel
          </button>
          <button
            onClick={handlePreview}
            disabled={loading === "preview" || transcript.trim().length < 20}
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent text-on-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-50 transition-all"
          >
            {loading === "preview" ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Detecting…
              </>
            ) : (
              "Continue"
            )}
          </button>
        </div>
      )}
    </div>
  );
}

function StepIndicator({ step }: { step: Step["kind"] }) {
  const steps = [
    { key: "input", label: "Input" },
    { key: "confirm", label: "Sender" },
    { key: "preview", label: "Preview" },
  ];
  const idx = steps.findIndex((s) => s.key === step);
  return (
    <div className="flex items-center gap-2 mb-4 text-[11px] text-fg-subtle">
      {steps.map((s, i) => (
        <div key={s.key} className="flex items-center gap-2">
          <span
            className={cn(
              "h-5 w-5 rounded-full grid place-items-center text-[10px] font-medium",
              i <= idx ? "bg-accent text-on-accent" : "bg-fg/10 text-fg-subtle",
            )}
          >
            {i + 1}
          </span>
          <span className={i === idx ? "text-fg font-medium" : ""}>{s.label}</span>
          {i < steps.length - 1 && <span className="text-fg-subtle">›</span>}
        </div>
      ))}
    </div>
  );
}

// =============================================================================
// Step 1: Input (paste or upload .txt)
// =============================================================================

function InputStep({
  transcript,
  setTranscript,
  filename,
  setFilename,
  onClear,
  setError,
}: {
  transcript: string;
  setTranscript: (v: string) => void;
  filename: string | null;
  setFilename: (v: string | null) => void;
  onClear: () => void;
  setError: (v: string | null) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setError(null);
    if (file.size > MAX_UPLOAD_CHARS * 2) {
      // size in bytes is a rough upper bound on chars; reject obvious oversize
      setError(
        `File too large (${Math.round(file.size / 1024)} KB). Max ${Math.round(MAX_UPLOAD_CHARS / 1024)} KB.`,
      );
      return;
    }
    try {
      const text = await file.text();
      if (text.length > MAX_UPLOAD_CHARS) {
        setError(
          `File too large (${Math.round(text.length / 1024)} KB). Max ${Math.round(MAX_UPLOAD_CHARS / 1024)} KB.`,
        );
        return;
      }
      setTranscript(text);
      setFilename(file.name);
    } catch (e) {
      setError(`Could not read file: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  const charCount = transcript.length;
  const isLarge = charCount > LARGE_FILE_WARN_THRESHOLD;

  return (
    <div>
      <p className="text-xs text-fg-muted mb-3">
        Upload a .txt chat history (WhatsApp/Telegram export) or paste messages.
        The transcript is analyzed once and then discarded — not stored.
      </p>

      {/* Upload button */}
      <div className="flex items-center gap-2 mb-3">
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border-strong bg-bg/40 px-3 py-1.5 text-xs text-fg-soft hover:bg-fg/5 transition-colors"
        >
          <Upload className="h-3.5 w-3.5" />
          Upload .txt
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".txt,text/plain"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
            e.target.value = "";
          }}
        />
        {filename && (
          <span className="inline-flex items-center gap-1.5 text-xs text-fg-soft bg-fg/5 px-2 py-1 rounded-lg">
            <FileText className="h-3 w-3" />
            <span className="truncate max-w-[160px]">{filename}</span>
            <button
              onClick={onClear}
              className="text-fg-subtle hover:text-fg"
              aria-label="Remove file"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        )}
        {transcript && !filename && (
          <button
            onClick={onClear}
            className="text-xs text-fg-muted hover:text-fg"
          >
            Clear
          </button>
        )}
      </div>

      <label className="block">
        <span className="text-xs font-medium text-fg-muted">
          Chat transcript {charCount > 0 && (
            <span className="text-fg-subtle">· {charCount.toLocaleString()} chars</span>
          )}
        </span>
        <textarea
          rows={10}
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          placeholder={`Paste here, or upload a .txt file.\n\nExamples that work well:\n[9/5/24, 10:23 PM] Anna: hey beb\n[9/5/24, 10:24 PM] Anna: udah makan?\n\nOr Telegram text export.`}
          className={cn(inputCls, "resize-none font-mono text-[12px]")}
        />
      </label>

      {isLarge && (
        <p className="mt-2 text-[11px] text-fg-soft">
          Large transcript detected. We&apos;ll sample representative messages from
          beginning, middle, and recent portions for analysis.
        </p>
      )}
    </div>
  );
}

// =============================================================================
// Step 2: Confirm sender
// =============================================================================

function ConfirmStep({
  preview,
  onBack,
  onAnalyze,
  loading,
}: {
  preview: PreviewParseResult;
  onBack: () => void;
  onAnalyze: (targetName: string | null) => void;
  loading: boolean;
}) {
  // Default to recommended sender, or "plain" mode if no senders
  const [selection, setSelection] = useState<string | "_plain_" | null>(
    preview.recommended_target_name ??
      (preview.senders.length === 0 ? "_plain_" : preview.senders[0]?.name ?? null),
  );

  return (
    <div>
      <p className="text-xs text-fg-muted mb-3">
        {preview.source_type === "plain"
          ? "No structured chat format detected. Will analyze as a single writing sample."
          : `Detected ${preview.message_count} messages. Which person's style do you want to analyze?`}
      </p>

      {preview.warnings.length > 0 && (
        <div className="mb-3 p-2.5 rounded-lg bg-fg/5 border border-border space-y-1">
          {preview.warnings.map((w, i) => (
            <p key={i} className="text-[11px] text-fg-soft flex items-start gap-1.5">
              <AlertCircle className="h-3 w-3 mt-0.5 shrink-0 text-fg-muted" />
              {w}
            </p>
          ))}
        </div>
      )}

      {preview.senders.length > 0 && (
        <div className="space-y-1.5 mb-3">
          {preview.senders.map((s) => (
            <SenderOption
              key={s.name}
              sender={s}
              selected={selection === s.name}
              onClick={() => setSelection(s.name)}
            />
          ))}
          <button
            onClick={() => setSelection("_plain_")}
            className={cn(
              "w-full text-left p-2.5 rounded-lg border-2 transition-all flex items-center gap-3",
              selection === "_plain_"
                ? "border-accent bg-accent-soft ring-2 ring-accent/20"
                : "border-border hover:border-border-strong hover:bg-fg/5",
            )}
          >
            <span
              className={cn(
                "h-4 w-4 rounded-full border-2 shrink-0 transition-all grid place-items-center",
                selection === "_plain_"
                  ? "border-accent bg-accent"
                  : "border-border-strong bg-transparent",
              )}
            >
              {selection === "_plain_" && (
                <span className="h-1.5 w-1.5 rounded-full bg-on-accent" />
              )}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-fg">Treat entire text as one writing sample</p>
              <p className="text-[11px] text-fg-muted">
                Ignore sender labels, analyze all messages together
              </p>
            </div>
          </button>
        </div>
      )}

      <div className="flex justify-between gap-2 pt-3 mt-3 border-t border-border">
        <button
          type="button"
          onClick={onBack}
          className="px-3 py-1.5 rounded-lg text-sm text-fg-muted hover:bg-fg/5"
        >
          Back
        </button>
        <button
          onClick={() =>
            onAnalyze(selection === "_plain_" ? null : selection)
          }
          disabled={loading || !selection}
          className="inline-flex items-center gap-1.5 rounded-lg bg-accent text-on-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-50 transition-all"
        >
          {loading ? (
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

function SenderOption({
  sender,
  selected,
  onClick,
}: {
  sender: PreviewSender;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left p-2.5 rounded-lg border-2 transition-all flex items-center gap-3",
        selected
          ? "border-accent bg-accent-soft ring-2 ring-accent/20"
          : "border-border hover:border-border-strong hover:bg-fg/5",
      )}
    >
      <span
        className={cn(
          "h-4 w-4 rounded-full border-2 shrink-0 transition-all grid place-items-center",
          selected ? "border-accent bg-accent" : "border-border-strong bg-transparent",
        )}
      >
        {selected && <span className="h-1.5 w-1.5 rounded-full bg-on-accent" />}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-fg truncate">
          {sender.name}
          {sender.recommended && (
            <span className="ml-2 text-[10px] uppercase tracking-wider text-accent font-medium">
              Recommended
            </span>
          )}
          {sender.is_likely_user && !sender.recommended && (
            <span className="ml-2 text-[10px] uppercase tracking-wider text-fg-subtle">
              Likely you
            </span>
          )}
        </p>
        <p className="text-[11px] text-fg-muted">{sender.count} messages</p>
      </div>
    </button>
  );
}

// =============================================================================
// Step 3: Preview & save
// =============================================================================

function PreviewStep({
  result,
  onSave,
  loading,
  onReanalyze,
}: {
  result: AnalyzeResult;
  onSave: (name: string) => void;
  loading: boolean;
  onReanalyze: () => void;
}) {
  const [profileName, setProfileName] = useState(result.suggested_name);
  const style = result.profile as StyleData;

  return (
    <div>
      <label className="block mb-3">
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

      {result.warnings.length > 0 && (
        <div className="mb-3 p-2.5 rounded-lg bg-fg/5 border border-border space-y-1">
          {result.warnings.map((w, i) => (
            <p key={i} className="text-[11px] text-fg-soft flex items-start gap-1.5">
              <AlertCircle className="h-3 w-3 mt-0.5 shrink-0 text-fg-muted" />
              {w}
            </p>
          ))}
        </div>
      )}

      <p className="text-[11px] text-fg-subtle mb-4">
        {result.sample_count} target messages · format: {result.source_type}
      </p>

      <div className="flex justify-end gap-2 pt-3 border-t border-border">
        <button
          type="button"
          onClick={onReanalyze}
          className="px-3 py-1.5 rounded-lg text-sm text-fg-muted hover:bg-fg/5"
        >
          Pick different sender
        </button>
        <button
          onClick={() => onSave(profileName)}
          disabled={loading || !profileName.trim()}
          className="inline-flex items-center gap-1.5 rounded-lg bg-accent text-on-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-50 transition-all"
        >
          {loading ? "Saving…" : "Save profile"}
        </button>
      </div>
    </div>
  );
}

// =============================================================================
// Profile card (existing, unchanged)
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
