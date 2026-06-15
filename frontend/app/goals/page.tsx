"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Pause, Plus, Target, Trash2, X } from "lucide-react";
import {
  type Goal,
  type GoalActionProposal,
  type GoalInput,
  type GoalSuggestion,
  confirmGoalActionProposal,
  confirmGoalSuggestion,
  createGoal,
  deleteGoal,
  dismissGoalActionProposal,
  dismissGoalSuggestion,
  listGoalActionProposals,
  listGoalSuggestions,
  listGoals,
  updateGoalStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { AppPageShell, AppPanel, AppToolbar } from "@/components/ui/app-page-shell";
import { useUserOwnedLabel } from "@/hooks/use-identity-owned-label";
import { useAssistantDisplayName } from "@/hooks/use-assistant-display-name";
import { BackToLastChat } from "@/components/navigation/back-to-last-chat";
import { createClient } from "@/lib/supabase/client";
import { readSnapshot, SNAPSHOT_MAX_AGE_MS, userScopedSnapshotKey, writeSnapshot } from "@/lib/snapshot-cache";

const HORIZONS: Goal["horizon"][] = ["week", "month", "quarter", "year", "multi_year", "life"];

const HORIZON_LABELS: Record<Goal["horizon"], string> = {
  week: "This week",
  month: "This month",
  quarter: "This quarter",
  year: "This year",
  multi_year: "Multi-year",
  life: "Lifetime",
};

const STATUS_LABELS: Record<Goal["status"] | "all", string> = {
  active: "Active",
  paused: "Paused",
  achieved: "Done",
  abandoned: "Dropped",
  all: "All",
};

type GoalsSnapshotData = {
  filter: Goal["status"] | "all";
  goals: Goal[];
  suggestions: GoalSuggestion[];
  actionProposals: GoalActionProposal[];
};

const LEGACY_GOALS_SNAPSHOT_PREFIX = "app:goals-snapshot:v1:";
const GOALS_SNAPSHOT_AREA = "goals";

function goalsSnapshotKey(
  keyPrefix: string,
  filter: Goal["status"] | "all",
): string {
  return `${keyPrefix}${filter}`;
}

function goalsSnapshotPrefixForUser(userId: string): string {
  return `${userScopedSnapshotKey({
    userId,
    area: GOALS_SNAPSHOT_AREA,
  })}:`;
}

function isGoalsSnapshotData(value: unknown): value is GoalsSnapshotData {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }

  const item = value as Partial<GoalsSnapshotData>;

  return (
    (item.filter === "active" ||
      item.filter === "paused" ||
      item.filter === "achieved" ||
      item.filter === "abandoned" ||
      item.filter === "all") &&
    Array.isArray(item.goals) &&
    Array.isArray(item.suggestions) &&
    Array.isArray(item.actionProposals)
  );
}

function readGoalsSnapshot(
  filter: Goal["status"] | "all",
  keyPrefix = LEGACY_GOALS_SNAPSHOT_PREFIX,
): GoalsSnapshotData | null {
  const snapshot = readSnapshot<GoalsSnapshotData>(
    goalsSnapshotKey(keyPrefix, filter),
    {
      filter,
      goals: [],
      suggestions: [],
      actionProposals: [],
    },
    isGoalsSnapshotData,
    { maxAgeMs: SNAPSHOT_MAX_AGE_MS.goals },
  );

  if (!snapshot || snapshot.data.filter !== filter) {
    return null;
  }

  return snapshot.data;
}

function writeGoalsSnapshot(
  filter: Goal["status"] | "all",
  payload: {
    goals: Goal[];
    suggestions: GoalSuggestion[];
    actionProposals: GoalActionProposal[];
  },
  keyPrefix = LEGACY_GOALS_SNAPSHOT_PREFIX,
) {
  writeSnapshot(goalsSnapshotKey(keyPrefix, filter), {
    filter,
    goals: payload.goals,
    suggestions: payload.suggestions,
    actionProposals: payload.actionProposals,
  });
}

function goalActionLabel(proposal: GoalActionProposal): string {
  const goalTitle = proposal.goals?.title || "this goal";

  switch (proposal.action_type) {
    case "mark_achieved":
      return `Mark “${goalTitle}” as done`;
    case "pause":
      return `Pause “${goalTitle}”`;
    case "resume":
      return `Resume “${goalTitle}”`;
    case "abandon":
      return `Mark “${goalTitle}” as dropped`;
    case "delete":
      return `Delete “${goalTitle}”`;
    case "update":
      return `Update “${goalTitle}”`;
    default:
      return `Review update for “${goalTitle}”`;
  }
}

function goalActionTone(proposal: GoalActionProposal): string {
  if (proposal.action_type === "delete") return "Destructive action — confirmation required";
  if (proposal.action_type === "update") return "Goal update — confirmation required";
  return "Status change — confirmation required";
}

export default function GoalsPage() {
  const assistantName = useAssistantDisplayName();
  const goalsEyebrow = useUserOwnedLabel("Goals");

  const [filter, setFilter] = useState<Goal["status"] | "all">("active");
  const [snapshotKeyPrefix, setSnapshotKeyPrefix] = useState(LEGACY_GOALS_SNAPSHOT_PREFIX);
  const [goals, setGoals] = useState<Goal[]>(() => readGoalsSnapshot("active")?.goals ?? []);
  const [suggestions, setSuggestions] = useState<GoalSuggestion[]>(
    () => readGoalsSnapshot("active")?.suggestions ?? [],
  );
  const [actionProposals, setActionProposals] = useState<GoalActionProposal[]>(
    () => readGoalsSnapshot("active")?.actionProposals ?? [],
  );

  const [loading, setLoading] = useState(() => !readGoalsSnapshot("active"));
  const [error, setError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [horizon, setHorizon] = useState<Goal["horizon"]>("quarter");
  const [weight, setWeight] = useState(5);
  const [saving, setSaving] = useState(false);

  const [actionProposalBusyId, setActionProposalBusyId] = useState<string | null>(null);
  const [actionProposalError, setActionProposalError] = useState<string | null>(null);

  function writeCurrentGoalsSnapshot(next: {
    goals?: Goal[];
    suggestions?: GoalSuggestion[];
    actionProposals?: GoalActionProposal[];
  }) {
    writeGoalsSnapshot(
      filter,
      {
        goals: next.goals ?? goals,
        suggestions: next.suggestions ?? suggestions,
        actionProposals: next.actionProposals ?? actionProposals,
      },
      snapshotKeyPrefix,
    );
  }

  const load = useCallback(async () => {
    const snapshot = readGoalsSnapshot(filter, snapshotKeyPrefix);

    if (snapshot) {
      setGoals(snapshot.goals);
      setSuggestions(snapshot.suggestions);
      setActionProposals(snapshot.actionProposals);
    }

    setLoading(true);
    setError(null);

    const [goalsResult, suggestionsResult, actionsResult] = await Promise.allSettled([
      listGoals(filter),
      listGoalSuggestions("pending"),
      listGoalActionProposals("pending"),
    ]);

    const nextGoals = goalsResult.status === "fulfilled" ? goalsResult.value : snapshot?.goals ?? [];
    const nextSuggestions =
      suggestionsResult.status === "fulfilled" ? suggestionsResult.value : snapshot?.suggestions ?? [];
    const nextActionProposals =
      actionsResult.status === "fulfilled" ? actionsResult.value : snapshot?.actionProposals ?? [];

    if (goalsResult.status === "fulfilled") {
      setGoals(nextGoals);
    } else {
      setGoals(nextGoals);
      setError(String(goalsResult.reason));
    }

    if (suggestionsResult.status === "fulfilled") {
      setSuggestions(nextSuggestions);
    } else {
      setSuggestions(nextSuggestions);
      console.warn("Goal suggestions failed to load", suggestionsResult.reason);
    }

    if (actionsResult.status === "fulfilled") {
      setActionProposals(nextActionProposals);
      setActionProposalError(null);
    } else {
      setActionProposals(nextActionProposals);
      setActionProposalError("Failed to load suggested goal updates.");
      console.warn("Goal action proposals failed to load", actionsResult.reason);
    }

    if (
      goalsResult.status === "fulfilled" ||
      suggestionsResult.status === "fulfilled" ||
      actionsResult.status === "fulfilled"
    ) {
      writeGoalsSnapshot(
        filter,
        {
          goals: nextGoals,
          suggestions: nextSuggestions,
          actionProposals: nextActionProposals,
        },
        snapshotKeyPrefix,
      );
    }

    setLoading(false);
  }, [filter, snapshotKeyPrefix]);

  useEffect(() => {
    let cancelled = false;

    async function resolveUserScopedSnapshotPrefix() {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (cancelled) return;

      const userId = session?.user?.id;
      if (!userId) return;

      const scopedPrefix = goalsSnapshotPrefixForUser(userId);
      const scopedSnapshot = readGoalsSnapshot(filter, scopedPrefix);

      if (scopedSnapshot) {
        setGoals(scopedSnapshot.goals);
        setSuggestions(scopedSnapshot.suggestions);
        setActionProposals(scopedSnapshot.actionProposals);
      } else if (goals.length > 0 || suggestions.length > 0 || actionProposals.length > 0) {
        writeGoalsSnapshot(
          filter,
          {
            goals,
            suggestions,
            actionProposals,
          },
          scopedPrefix,
        );
      }

      setSnapshotKeyPrefix(scopedPrefix);
    }

    void resolveUserScopedSnapshotPrefix();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (loading) return;

    writeGoalsSnapshot(
      filter,
      {
        goals,
        suggestions,
        actionProposals,
      },
      snapshotKeyPrefix,
    );
  }, [actionProposals, filter, goals, loading, snapshotKeyPrefix, suggestions]);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const cleanedTitle = title.trim();
    if (!cleanedTitle) return;

    setSaving(true);
    setError(null);

    const input: GoalInput = {
      title: cleanedTitle,
      description: description.trim() || null,
      horizon,
      emotional_weight: weight,
      target_date: null,
    };

    try {
      const created = await createGoal(input);
      setGoals((current) => {
        const nextGoals = filter === "all" || filter === created.status ? [created, ...current] : current;
        writeCurrentGoalsSnapshot({ goals: nextGoals });
        return nextGoals;
      });
      setTitle("");
      setDescription("");
      setHorizon("quarter");
      setWeight(5);
      setShowForm(false);
    } catch (err) {
      console.error(err);
      setError("Failed to create goal.");
    } finally {
      setSaving(false);
    }
  }

  async function handleStatus(id: string, nextStatus: Goal["status"]) {
    const previous = goals;
    setGoals((current) => {
      const nextGoals = current
        .map((goal) => (goal.id === id ? { ...goal, status: nextStatus } : goal))
        .filter((goal) => filter === "all" || goal.status === filter);
      writeCurrentGoalsSnapshot({ goals: nextGoals });
      return nextGoals;
    });

    try {
      await updateGoalStatus(id, nextStatus);
    } catch (err) {
      console.error(err);
      setGoals(previous);
      writeCurrentGoalsSnapshot({ goals: previous });
      setError("Failed to update goal status.");
    }
  }

  async function handleDelete(id: string) {
    const confirmed = window.confirm("Delete this goal? This cannot be undone.");
    if (!confirmed) return;

    const previous = goals;
    setGoals((current) => {
      const nextGoals = current.filter((goal) => goal.id !== id);
      writeCurrentGoalsSnapshot({ goals: nextGoals });
      return nextGoals;
    });

    try {
      await deleteGoal(id);
    } catch (err) {
      console.error(err);
      setGoals(previous);
      writeCurrentGoalsSnapshot({ goals: previous });
      setError("Failed to delete goal.");
    }
  }

  async function handleConfirmSuggestion(id: string) {
    const previousSuggestions = suggestions;
    setSuggestions((current) => current.filter((item) => item.id !== id));

    try {
      const created = await confirmGoalSuggestion(id);
      if (filter === "all" || filter === created.status) {
        setGoals((current) => [created, ...current]);
      }
    } catch (err) {
      console.error(err);
      setSuggestions(previousSuggestions);
      setError("Failed to confirm goal suggestion.");
    }
  }

  async function handleDismissSuggestion(id: string) {
    const previousSuggestions = suggestions;
    setSuggestions((current) => {
      const nextSuggestions = current.filter((item) => item.id !== id);
      writeCurrentGoalsSnapshot({ suggestions: nextSuggestions });
      return nextSuggestions;
    });

    try {
      await dismissGoalSuggestion(id);
    } catch (err) {
      console.error(err);
      setSuggestions(previousSuggestions);
      writeCurrentGoalsSnapshot({ suggestions: previousSuggestions });
      setError("Failed to dismiss goal suggestion.");
    }
  }

  async function handleConfirmGoalActionProposal(id: string) {
    try {
      setActionProposalBusyId(id);
      setActionProposalError(null);
      await confirmGoalActionProposal(id);
      setActionProposals((current) => current.filter((item) => item.id !== id));
      await load();
    } catch (err) {
      console.error(err);
      setActionProposalError("Failed to confirm goal update.");
    } finally {
      setActionProposalBusyId(null);
    }
  }

  async function handleDismissGoalActionProposal(id: string) {
    try {
      setActionProposalBusyId(id);
      setActionProposalError(null);
      await dismissGoalActionProposal(id);
      setActionProposals((current) => {
        const nextActionProposals = current.filter((item) => item.id !== id);
        writeCurrentGoalsSnapshot({ actionProposals: nextActionProposals });
        return nextActionProposals;
      });
    } catch (err) {
      console.error(err);
      setActionProposalError("Failed to dismiss goal update.");
    } finally {
      setActionProposalBusyId(null);
    }
  }

  return (
    <AppPageShell
      eyebrow={goalsEyebrow}
      title="Goals"
      description={`Tell ${assistantName || "your assistant"} what you are working toward, so she can help you make better plans and decisions.`}
      maxWidthClassName="max-w-5xl"
      actions={
        <BackToLastChat className="inline-flex h-10 items-center justify-center rounded-full border border-border bg-fg/[0.035] px-4 text-sm font-medium text-fg-muted shadow-sm transition hover:bg-fg/5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 active:scale-[0.98]">
          Back to Chat
        </BackToLastChat>
      }
    >
      {loading && (goals.length > 0 || suggestions.length > 0 || actionProposals.length > 0) ? (
        <div className="mb-3 rounded-2xl border border-border bg-fg/[0.025] px-4 py-2 text-xs text-fg-muted">
          Showing saved Goals snapshot while refreshing latest data…
        </div>
      ) : null}

      <div className="mb-4">
        <AppToolbar>
        <button
          type="button"
          onClick={() => setShowForm((value) => !value)}
          className="inline-flex items-center gap-2 rounded-full bg-slate-950 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-slate-800 dark:bg-white dark:text-slate-950 dark:hover:bg-zinc-200"
        >
          <Plus className="h-4 w-4" />
          New goal
        </button>

        <div className="flex w-full gap-1 overflow-x-auto rounded-full border border-slate-200/70 bg-white/65 p-1 dark:border-white/10 dark:bg-black/20 md:w-auto">
          {(["active", "paused", "achieved", "abandoned", "all"] as const).map((status) => (
            <button
              key={status}
              type="button"
              onClick={() => setFilter(status)}
              className={cn(
                "whitespace-nowrap rounded-full px-3 py-2 text-xs font-medium transition-colors",
                filter === status
                  ? "bg-slate-950 text-white dark:bg-white dark:text-slate-950"
                  : "text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white",
              )}
            >
              {STATUS_LABELS[status]}
            </button>
          ))}
        </div>
        </AppToolbar>
      </div>

      {showForm ? (
        <form
          onSubmit={handleCreate}
          className="mb-4 rounded-[1.5rem] border border-slate-200/70 bg-white/75 p-5 shadow-xl shadow-slate-900/5 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.04]"
        >
          <label className="mb-4 block">
            <span className="text-sm font-medium text-slate-900 dark:text-white">Goal</span>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="What do you want to work toward?"
              className="mt-2 w-full rounded-2xl border border-slate-200/70 bg-white/80 px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white"
            />
          </label>

          <label className="mb-4 block">
            <span className="text-sm font-medium text-slate-900 dark:text-white">Description</span>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Add context, target, or motivation"
              rows={3}
              className="mt-2 w-full resize-none rounded-2xl border border-slate-200/70 bg-white/80 px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white"
            />
          </label>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="text-sm font-medium text-slate-900 dark:text-white">Horizon</span>
              <select
                value={horizon}
                onChange={(event) => setHorizon(event.target.value as Goal["horizon"])}
                className="mt-2 w-full rounded-2xl border border-slate-200/70 bg-white/80 px-3 py-2 text-sm text-slate-900 outline-none dark:border-white/10 dark:bg-black/25 dark:text-white"
              >
                {HORIZONS.map((item) => (
                  <option key={item} value={item}>
                    {HORIZON_LABELS[item]}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-sm font-medium text-slate-900 dark:text-white">
                Emotional weight: {weight}
              </span>
              <input
                type="range"
                min={1}
                max={10}
                value={weight}
                onChange={(event) => setWeight(Number(event.target.value))}
                className="mt-4 w-full"
              />
            </label>
          </div>

          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="rounded-full border border-border px-4 py-2 text-sm text-fg-muted transition hover:bg-fg/5 hover:text-fg"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || !title.trim()}
              className="rounded-full bg-fg px-4 py-2 text-sm font-medium text-bg transition hover:opacity-90 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save goal"}
            </button>
          </div>
        </form>
      ) : null}

      {actionProposals.length > 0 || actionProposalError ? (
        <AppPanel className="mb-4">
          <div className="mb-3">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-fg-subtle">
              Suggested goal updates
            </p>
            <h2 className="mt-1 text-base font-semibold text-fg">
              Review changes before applying them
            </h2>
          </div>

          {actionProposalError ? (
            <p className="mb-3 rounded-2xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-300">
              {actionProposalError}
            </p>
          ) : null}

          <div className="space-y-2">
            {actionProposals.map((proposal) => (
              <div
                key={proposal.id}
                className="flex flex-col gap-3 rounded-2xl border border-border bg-fg/[0.025] p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-fg">{goalActionLabel(proposal)}</p>
                  <p className="mt-1 text-xs text-fg-muted">
                    {proposal.assistant_reason || goalActionTone(proposal)}
                  </p>
                </div>

                <div className="flex shrink-0 gap-2">
                  <button
                    type="button"
                    disabled={actionProposalBusyId === proposal.id}
                    onClick={() => handleDismissGoalActionProposal(proposal.id)}
                    className="rounded-full border border-border bg-transparent px-3 py-1.5 text-xs font-medium text-fg-muted transition hover:bg-fg/5 hover:text-fg disabled:opacity-50"
                  >
                    Dismiss
                  </button>
                  <button
                    type="button"
                    disabled={actionProposalBusyId === proposal.id}
                    onClick={() => handleConfirmGoalActionProposal(proposal.id)}
                    className="rounded-full bg-fg px-3 py-1.5 text-xs font-medium text-bg transition hover:opacity-90 disabled:opacity-50"
                  >
                    Confirm
                  </button>
                </div>
              </div>
            ))}
          </div>
        </AppPanel>
      ) : null}

      {suggestions.length > 0 ? (
        <AppPanel className="mb-4">
          <div className="border-b border-slate-200/70 px-5 py-4 dark:border-white/10">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-700 dark:text-cyan-300">
              Suggested by {assistantName || "your assistant"}
            </p>
            <p className="mt-1 text-sm text-slate-600 dark:text-zinc-400">
              These came from your conversations. Confirm only the ones you want {assistantName || "your assistant"} to track.
            </p>
          </div>

          <div className="divide-y divide-slate-200/70 dark:divide-white/10">
            {suggestions.map((suggestion) => (
              <article key={suggestion.id} className="p-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-950 dark:text-white">
                      {suggestion.title}
                    </p>
                    {suggestion.description ? (
                      <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-zinc-300">
                        {suggestion.description}
                      </p>
                    ) : null}
                    {suggestion.assistant_reason ? (
                      <p className="mt-2 text-xs text-slate-500 dark:text-zinc-500">
                        {suggestion.assistant_reason}
                      </p>
                    ) : null}
                  </div>

                  <div className="flex shrink-0 gap-2">
                    <button
                      type="button"
                      onClick={() => handleDismissSuggestion(suggestion.id)}
                      className="inline-flex items-center gap-1 rounded-full border border-slate-200/70 px-3 py-1.5 text-xs text-slate-500 transition hover:bg-slate-50 hover:text-slate-950 dark:border-white/10 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white"
                    >
                      <X className="h-3.5 w-3.5" />
                      Dismiss
                    </button>
                    <button
                      type="button"
                      onClick={() => handleConfirmSuggestion(suggestion.id)}
                      className="inline-flex items-center gap-1 rounded-full bg-slate-950 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-slate-800 dark:bg-white dark:text-slate-950"
                    >
                      <Check className="h-3.5 w-3.5" />
                      Confirm
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </AppPanel>
      ) : null}

      <AppPanel>
        {loading && goals.length === 0 && suggestions.length === 0 && actionProposals.length === 0 ? (
          <div className="p-8 text-center text-sm text-fg-muted">Loading goals...</div>
        ) : error && goals.length === 0 ? (
          <div className="p-8 text-center text-sm text-red-600 dark:text-red-300">{error}</div>
        ) : goals.length === 0 ? (
          <div className="p-10 text-center">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-fg/[0.04] text-fg-muted">
              <Target className="h-5 w-5" />
            </div>
            <h2 className="mt-4 text-lg font-semibold text-fg">No goals here yet</h2>
            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-fg-muted">
              Add a goal or confirm one of {assistantName || "your assistant"}’s suggestions when you are ready.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-200/70 dark:divide-white/10">
            {goals.map((goal) => (
              <article key={goal.id} className="p-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-slate-950 dark:text-white">{goal.title}</p>
                      <span className="rounded-full bg-fg/[0.06] px-2 py-1 text-[11px] text-fg-muted">
                        {STATUS_LABELS[goal.status]}
                      </span>
                      <span className="rounded-full bg-fg/[0.06] px-2 py-1 text-[11px] text-fg-muted">
                        {HORIZON_LABELS[goal.horizon]}
                      </span>
                    </div>

                    {goal.description ? (
                      <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-zinc-300">
                        {goal.description}
                      </p>
                    ) : null}

                    <p className="mt-3 text-xs text-slate-500 dark:text-zinc-500">
                      Emotional weight: {goal.emotional_weight ?? 5}/10
                    </p>
                  </div>

                  <div className="flex shrink-0 flex-wrap gap-2">
                    {goal.status !== "achieved" ? (
                      <button
                        type="button"
                        onClick={() => handleStatus(goal.id, "achieved")}
                        className="inline-flex items-center gap-1 rounded-full border border-slate-200/70 px-3 py-1.5 text-xs text-slate-500 transition hover:bg-slate-50 hover:text-slate-950 dark:border-white/10 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white"
                      >
                        <Check className="h-3.5 w-3.5" />
                        Done
                      </button>
                    ) : null}

                    {goal.status === "paused" ? (
                      <button
                        type="button"
                        onClick={() => handleStatus(goal.id, "active")}
                        className="inline-flex items-center gap-1 rounded-full border border-slate-200/70 px-3 py-1.5 text-xs text-slate-500 transition hover:bg-slate-50 hover:text-slate-950 dark:border-white/10 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white"
                      >
                        <Target className="h-3.5 w-3.5" />
                        Resume
                      </button>
                    ) : goal.status === "active" ? (
                      <button
                        type="button"
                        onClick={() => handleStatus(goal.id, "paused")}
                        className="inline-flex items-center gap-1 rounded-full border border-slate-200/70 px-3 py-1.5 text-xs text-slate-500 transition hover:bg-slate-50 hover:text-slate-950 dark:border-white/10 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white"
                      >
                        <Pause className="h-3.5 w-3.5" />
                        Pause
                      </button>
                    ) : null}

                    {goal.status !== "abandoned" ? (
                      <button
                        type="button"
                        onClick={() => handleStatus(goal.id, "abandoned")}
                        className="inline-flex items-center gap-1 rounded-full border border-slate-200/70 px-3 py-1.5 text-xs text-slate-500 transition hover:bg-slate-50 hover:text-slate-950 dark:border-white/10 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white"
                      >
                        <X className="h-3.5 w-3.5" />
                        Drop
                      </button>
                    ) : null}

                    <button
                      type="button"
                      onClick={() => handleDelete(goal.id)}
                      className="inline-flex items-center gap-1 rounded-full border border-red-500/20 px-3 py-1.5 text-xs text-red-600 transition hover:bg-red-500/10 dark:text-red-300"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      Delete
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </AppPanel>
    </AppPageShell>
  );
}
