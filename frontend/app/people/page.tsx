"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Heart, Plus, Trash2, Users } from "lucide-react";
import {
  type Person,
  type PersonInput,
  createPerson,
  deletePerson,
  listPeople,
} from "@/lib/api";
import { cn } from "@/lib/utils";

export default function PeoplePage() {
  const [people, setPeople] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [relationship, setRelationship] = useState("");
  const [importance, setImportance] = useState(5);
  const [emotional, setEmotional] = useState(5);
  const [birthday, setBirthday] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listPeople()
      .then((data) => !cancelled && setPeople(data))
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const input: PersonInput = {
        name: name.trim(),
        relationship: relationship.trim() || null,
        importance,
        emotional_significance: emotional,
        birthday: birthday || null,
      };
      const created = await createPerson(input);
      setPeople((prev) =>
        [...prev, created].sort((a, b) => b.importance - a.importance),
      );
      setName("");
      setRelationship("");
      setImportance(5);
      setEmotional(5);
      setBirthday("");
      setShowForm(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Remove this person and all notes about them?")) return;
    const prev = people;
    setPeople((p) => p.filter((x) => x.id !== id));
    try {
      await deletePerson(id);
    } catch (e) {
      setPeople(prev);
      setError(String(e));
    }
  }

  return (
    <main className="min-h-dvh">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-5 sm:py-8 fade-up">
        <Link
          href="/chat"
          className="inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg mb-6 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to chat
        </Link>

        <div className="flex items-start justify-between mb-2">
          <h1 className="text-3xl font-semibold text-fg tracking-tighter">People</h1>
          <button
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-xl bg-accent text-on-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover transition-all active:scale-[0.98] shadow-md shadow-accent/25"
          >
            <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
            Add person
          </button>
        </div>
        <p className="text-base text-fg-muted mb-6">
          People who matter in your life. The assistant uses this to remember context.
        </p>

        {showForm && (
          <form onSubmit={handleCreate} className="glass rounded-2xl p-5 mb-6 fade-up">
            <div className="grid sm:grid-cols-2 gap-4 mb-4">
              <label className="block">
                <span className="text-sm font-medium text-fg">Name</span>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Anna"
                  className={inputCls}
                />
              </label>
              <label className="block">
                <span className="text-sm font-medium text-fg">Relationship</span>
                <input
                  type="text"
                  value={relationship}
                  onChange={(e) => setRelationship(e.target.value)}
                  placeholder="wife, co-founder, mother…"
                  className={inputCls}
                />
              </label>
            </div>

            <div className="grid sm:grid-cols-2 gap-4 mb-4">
              <label className="block">
                <span className="text-sm font-medium text-fg">
                  Importance ({importance}/10)
                </span>
                <span className="block text-xs text-fg-muted mt-0.5">
                  How present in your daily life
                </span>
                <input
                  type="range"
                  min={1}
                  max={10}
                  value={importance}
                  onChange={(e) => setImportance(Number(e.target.value))}
                  className="mt-2 w-full accent-accent"
                />
              </label>
              <label className="block">
                <span className="text-sm font-medium text-fg">
                  Emotional significance ({emotional}/10)
                </span>
                <span className="block text-xs text-fg-muted mt-0.5">
                  How much they matter, regardless of frequency
                </span>
                <input
                  type="range"
                  min={1}
                  max={10}
                  value={emotional}
                  onChange={(e) => setEmotional(Number(e.target.value))}
                  className="mt-2 w-full accent-accent"
                />
              </label>
            </div>

            <label className="block mb-4">
              <span className="text-sm font-medium text-fg">Birthday (optional)</span>
              <input
                type="date"
                value={birthday}
                onChange={(e) => setBirthday(e.target.value)}
                className={inputCls}
              />
            </label>

            <div className="flex justify-end gap-2 pt-2 border-t border-border">
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="px-3 py-1.5 rounded-lg text-sm text-fg-muted hover:bg-fg/5"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving || !name.trim()}
                className="inline-flex items-center gap-1.5 rounded-lg bg-accent text-on-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-50 transition-all"
              >
                {saving ? "Saving…" : "Add"}
              </button>
            </div>
          </form>
        )}

        {error && <p className="text-sm text-danger mb-4">{error}</p>}

        {loading ? (
          <p className="text-sm text-fg-muted">Loading…</p>
        ) : people.length === 0 ? (
          <div className="text-center py-12 glass rounded-2xl">
            <Users className="h-6 w-6 text-fg-subtle mx-auto mb-2 opacity-60" />
            <p className="text-sm text-fg-muted">No one added yet.</p>
            <p className="text-xs text-fg-subtle mt-1">
              Start with the few people closest to you.
            </p>
          </div>
        ) : (
          <ul className="space-y-2">
            {people.map((p) => (
              <li key={p.id} className="group glass rounded-xl p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-fg">{p.name}</p>
                    {p.relationship && (
                      <p className="text-xs text-fg-muted mt-0.5">{p.relationship}</p>
                    )}
                    <div className="mt-2 flex items-center gap-3 text-xs text-fg-muted">
                      <span>importance {p.importance}/10</span>
                      <span className="inline-flex items-center gap-1">
                        <Heart className="h-3 w-3" />
                        {p.emotional_significance}/10
                      </span>
                      {p.birthday && (
                        <span className="text-fg-subtle">
                          🎂 {new Date(p.birthday).toLocaleDateString(undefined, {
                            month: "short",
                            day: "numeric",
                          })}
                        </span>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(p.id)}
                    className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-danger transition-opacity"
                    aria-label="Delete person"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}

const inputCls =
  "mt-1.5 w-full rounded-xl border border-border-strong bg-bg/40 backdrop-blur-sm px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all";
