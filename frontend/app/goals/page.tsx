"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Check, Pause, Plus, Target, Trash2, X } from "lucide-react";
import {
  type Goal,
  type GoalInput,
  createGoal,
  deleteGoal,
  listGoals,
  updateGoalStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { BackToChatButton } from "@/components/settings/back-to-chat-button";

const HORIZONS: Goal["horizon"][] = ["week", "month", "quarter", "year", "multi_year", "life"];
const HORIZON_LABELS: Record<Goal["horizon"], string> = {
  week: "This week",
  month: "This month",
  quarter: "This quarter",
  year: "This year",
  multi_year: "Multi-year",
  life: "Lifetime",
};

export default function GoalsPage() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Goal["status"] | "all">("active");
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // form state
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [horizon, setHorizon] = useState<Goal["horizon"]>("quarter");
  const [weight, setWeight] = useState(5);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listGoals(filter)
      .then((data) => !cancelled && setGoals(data))
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [filter]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const input: GoalInput = {
        title: title.trim(),
        description: description.trim() || null,
        horizon,
        emotional_weight: weight,
      };
      const created = await createGoal(input);
      setGoals((prev) => [created, ...prev]);
      setTitle("");
      setDescription("");
      setShowForm(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleStatus(id: string, status: Goal["status"]) {
    const prev = goals;
    setGoals((g) => g.map((x) => (x.id === id ? { ...x, status } : x)));
    try {
      await updateGoalStatus(id, status);
      if (filter !== "all" && status !== filter) {
        setGoals((g) => g.filter((x) => x.id !== id));
      }
    } catch (e) {
      setGoals(prev);
      setError(String(e));
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this goal? Check-ins on it will also be removed.")) return;
    const prev = goals;
    setGoals((g) => g.filter((x) => x.id !== id));
    try {
      await deleteGoal(id);
    } catch (e) {
      setGoals(prev);
      setError(String(e));
    }
  }

  return (
    <main className="min-h-dvh">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-5 sm:py-8 fade-up">
        <BackToChatButton />

        <div className="flex items-start justify-between mb-2">
          <h1 className="text-3xl font-semibold text-fg tracking-tighter">Goals</h1>
          <button
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-xl bg-accent text-on-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover transition-all active:scale-[0.98] shadow-md shadow-accent/25"
          >
            <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
            New goal
          </button>
        </div>
        <p className="text-base text-fg-muted mb-6">
          Where you&apos;re heading. The assistant uses these to reason about decisions.
        </p>

        {/* Filter tabs */}
        <div className="flex gap-1 mb-6">
          {(["active", "paused", "achieved", "abandoned", "all"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={cn(
                "px-3 py-1 rounded-lg text-xs font-medium transition-colors",
                filter === s
                  ? "bg-accent-soft text-fg"
                  : "text-fg-muted hover:bg-fg/5 hover:text-fg",
              )}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Create form */}
        {showForm && (
          <form onSubmit={handleCreate} className="glass rounded-2xl p-5 mb-6 fade-up">
            <label className="block mb-4">
              <span className="text-sm font-medium text-fg">Title</span>
              <input
                type="text"
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Get back in shape"
                className={inputCls}
              />
            </label>

            <label className="block mb-4">
              <span className="text-sm font-medium text-fg">Why this matters (optional)</span>
              <textarea
                rows={2}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Energy for the long haul, not aesthetics"
                className={cn(inputCls, "resize-none")}
              />
            </label>

            <div className="grid grid-cols-2 gap-4 mb-4">
              <label className="block">
                <span className="text-sm font-medium text-fg">Horizon</span>
                <select
                  value={horizon}
                  onChange={(e) => setHorizon(e.target.value as Goal["horizon"])}
                  className={inputCls}
                >
                  {HORIZONS.map((h) => (
                    <option key={h} value={h}>
                      {HORIZON_LABELS[h]}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="text-sm font-medium text-fg">
                  Emotional weight ({weight})
                </span>
                <input
                  type="range"
                  min={1}
                  max={10}
                  value={weight}
                  onChange={(e) => setWeight(Number(e.target.value))}
                  className="mt-3 w-full accent-accent"
                />
              </label>
            </div>

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
                disabled={saving || !title.trim()}
                className="inline-flex items-center gap-1.5 rounded-lg bg-accent text-on-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-50 transition-all"
              >
                {saving ? "Saving…" : "Create"}
              </button>
            </div>
          </form>
        )}

        {error && <p className="text-sm text-danger mb-4">{error}</p>}

        {/* List */}
        {loading ? (
          <p className="text-sm text-fg-muted">Loading…</p>
        ) : goals.length === 0 ? (
          <div className="text-center py-12 glass rounded-2xl">
            <Target className="h-6 w-6 text-fg-subtle mx-auto mb-2 opacity-60" />
            <p className="text-sm text-fg-muted">No {filter !== "all" ? filter : ""} goals.</p>
          </div>
        ) : (
          <ul className="space-y-2">
            {goals.map((g) => (
              <li key={g.id} className="group glass rounded-xl p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-fg break-words">{g.title}</p>
                    {g.description && (
                      <p className="text-xs text-fg-muted mt-1">{g.description}</p>
                    )}
                    <div className="mt-2 flex items-center gap-2 text-xs text-fg-muted">
                      <span className="rounded-md px-1.5 py-0.5 text-[10px] font-medium bg-accent-soft border border-accent/20 text-fg-soft">
                        {HORIZON_LABELS[g.horizon]}
                      </span>
                      <span>weight {g.emotional_weight}/10</span>
                      {g.status !== "active" && (
                        <span className="text-fg-subtle">· {g.status}</span>
                      )}
                    </div>
                  </div>
                  <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-opacity">
                    {g.status === "active" && (
                      <>
                        <IconBtn
                          onClick={() => handleStatus(g.id, "achieved")}
                          label="Mark achieved"
                          icon={<Check className="h-3.5 w-3.5" />}
                        />
                        <IconBtn
                          onClick={() => handleStatus(g.id, "paused")}
                          label="Pause"
                          icon={<Pause className="h-3.5 w-3.5" />}
                        />
                      </>
                    )}
                    {g.status === "paused" && (
                      <IconBtn
                        onClick={() => handleStatus(g.id, "active")}
                        label="Resume"
                        icon={<Check className="h-3.5 w-3.5" />}
                      />
                    )}
                    {(g.status === "achieved" || g.status === "abandoned") && (
                      <IconBtn
                        onClick={() => handleStatus(g.id, "active")}
                        label="Reopen"
                        icon={<X className="h-3.5 w-3.5" />}
                      />
                    )}
                    <IconBtn
                      onClick={() => handleDelete(g.id)}
                      label="Delete"
                      icon={<Trash2 className="h-3.5 w-3.5" />}
                      danger
                    />
                  </div>
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

function IconBtn({
  onClick,
  icon,
  label,
  danger,
}: {
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className={cn(
        "h-7 w-7 grid place-items-center rounded-md transition-colors",
        danger
          ? "text-fg-subtle hover:text-danger hover:bg-danger-soft"
          : "text-fg-muted hover:text-fg hover:bg-fg/5",
      )}
    >
      {icon}
    </button>
  );
}
