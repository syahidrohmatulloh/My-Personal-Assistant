"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Plus, Sparkles, Trash2, User } from "lucide-react";
import {
  type Memory,
  clearAllMemories,
  createMemory,
  deleteMemory,
  listMemories,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const KIND_LABELS: Record<Memory["kind"], string> = {
  fact: "Fact",
  preference: "Preference",
  context: "Context",
};

export default function MemoriesPage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [newContent, setNewContent] = useState("");
  const [newKind, setNewKind] = useState<Memory["kind"]>("fact");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listMemories()
      .then((data) => !cancelled && setMemories(data))
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const content = newContent.trim();
    if (!content) return;
    setAdding(true);
    setError(null);
    try {
      const created = await createMemory(content, newKind);
      setMemories((prev) => [created, ...prev]);
      setNewContent("");
    } catch (e) {
      setError(String(e));
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this memory?")) return;
    const prev = memories;
    setMemories((m) => m.filter((x) => x.id !== id));
    try {
      await deleteMemory(id);
    } catch (e) {
      setMemories(prev);
      setError(String(e));
    }
  }

  async function handleClearAll() {
    if (
      !confirm(`Permanently delete all ${memories.length} memories? This cannot be undone.`)
    )
      return;
    const prev = memories;
    setMemories([]);
    try {
      await clearAllMemories();
    } catch (e) {
      setMemories(prev);
      setError(String(e));
    }
  }

  return (
    <main className="min-h-dvh">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-5 sm:py-8 fade-up">
        <div className="flex items-center justify-between mb-6">
          <Link
            href="/chat"
            className="inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to chat
          </Link>
          {memories.length > 0 && (
            <button
              onClick={handleClearAll}
              className="text-xs text-fg-muted hover:text-danger transition-colors"
            >
              Clear all
            </button>
          )}
        </div>

        <h1 className="text-3xl font-semibold text-fg mb-1 tracking-tighter">Memories</h1>
        <p className="text-base text-fg-muted mb-8">
          What I remember about you across conversations.
        </p>

        {/* Add form */}
        <form onSubmit={handleAdd} className="glass rounded-2xl p-5 mb-8">
          <label className="block">
            <span className="text-sm font-medium text-fg">Add a memory</span>
            <textarea
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              rows={2}
              placeholder="e.g. I'm a vegetarian"
              className="mt-2 w-full resize-none rounded-xl border border-border-strong bg-bg/40 backdrop-blur-sm px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all"
            />
          </label>
          <div className="mt-3 flex items-center justify-between gap-3">
            <select
              value={newKind}
              onChange={(e) => setNewKind(e.target.value as Memory["kind"])}
              className="rounded-lg border border-border-strong bg-bg/60 backdrop-blur-sm px-2.5 py-1.5 text-sm text-fg focus:outline-none focus:border-accent"
            >
              <option value="fact">Fact</option>
              <option value="preference">Preference</option>
              <option value="context">Context</option>
            </select>
            <button
              type="submit"
              disabled={adding || !newContent.trim()}
              className="inline-flex items-center gap-1.5 rounded-xl bg-accent text-on-accent px-3.5 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-50 transition-all active:scale-[0.98] shadow-md shadow-accent/25"
            >
              <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
              {adding ? "Saving…" : "Add"}
            </button>
          </div>
        </form>

        {error && <p className="text-sm text-danger mb-4">{error}</p>}

        {/* List */}
        {loading ? (
          <p className="text-sm text-fg-muted">Loading…</p>
        ) : memories.length === 0 ? (
          <div className="text-center py-12 text-fg-muted glass rounded-2xl">
            <Sparkles className="h-6 w-6 text-fg-subtle mx-auto mb-2 opacity-60" />
            <p className="text-sm">No memories yet.</p>
            <p className="text-xs mt-1 text-fg-subtle">
              I&apos;ll remember things as we chat, or you can add them manually above.
            </p>
          </div>
        ) : (
          <ul className="space-y-2">
            {memories.map((m) => (
              <li
                key={m.id}
                className="group glass rounded-xl p-3.5 flex items-start gap-3"
              >
                <div className="mt-0.5">
                  {m.source === "manual" ? (
                    <User className="h-4 w-4 text-fg-muted" />
                  ) : (
                    <Sparkles className="h-4 w-4 text-accent" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-fg break-words">{m.content}</p>
                  <div className="mt-1.5 flex items-center gap-2 text-xs text-fg-muted">
                    <span
                      className={cn(
                        "rounded-md px-1.5 py-0.5 text-[10px] font-medium border",
                        "bg-accent-soft border-accent/20 text-fg-soft",
                      )}
                    >
                      {KIND_LABELS[m.kind]}
                    </span>
                    <span>
                      {m.source === "auto" ? "auto" : "manual"} ·{" "}
                      {new Date(m.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(m.id)}
                  className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-danger transition-opacity"
                  aria-label="Delete memory"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
