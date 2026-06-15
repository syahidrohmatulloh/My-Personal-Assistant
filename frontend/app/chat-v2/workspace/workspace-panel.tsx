"use client";

import {
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  RotateCcw,
  Settings2,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import type { AssistantMode } from "@/lib/api";
import { cardsForMode, type WorkspaceCardDefinition } from "./cards";
import { modeKey, type WorkspaceCardId, type WorkspaceContext } from "./types";
import { useWorkspacePreferences } from "./use-workspace-preferences";

export function WorkspacePanel({
  mode,
  context,
  onPrompt,
}: {
  mode: AssistantMode;
  context: WorkspaceContext;
  onPrompt?: (prompt: string) => void;
}) {
  const { preferences, toggleCard, moveCard, resetMode } = useWorkspacePreferences();
  const [customizing, setCustomizing] = useState(false);
  const isChief = mode === "chief_of_staff";
  const modePreferences = preferences[modeKey(mode)];

  const orderedCards = useMemo(() => {
    const availableCards = cardsForMode(mode);
    const byId = new Map(availableCards.map((card) => [card.id, card]));
    const ordered = modePreferences.order
      .map((id) => byId.get(id))
      .filter((card): card is WorkspaceCardDefinition => Boolean(card));
    const orderedIds = new Set(ordered.map((card) => card.id));
    const missingDefaultCards = availableCards.filter(
      (card) => card.defaultVisible && !orderedIds.has(card.id),
    );

    return [...missingDefaultCards, ...ordered];
  }, [mode, modePreferences.order]);

  const hiddenIds = useMemo(
    () => new Set<WorkspaceCardId>(modePreferences.hidden),
    [modePreferences.hidden],
  );
  const visibleCards = orderedCards.filter((card) => !hiddenIds.has(card.id));
  const quickLinks = [
    { href: "/goals", label: "Goals" },
    { href: "/journal", label: "Journal" },
    { href: "/people", label: "People" },
  ];

  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-between px-1">
        <p
          className={[
            "text-[11px] font-semibold uppercase tracking-[0.24em]",
            isChief ? "text-slate-500" : "text-stone-400",
          ].join(" ")}
        >
          Workspace
        </p>
        <button
          type="button"
          onClick={() => setCustomizing((value) => !value)}
          className={[
            "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-medium shadow-sm backdrop-blur transition active:scale-[0.98]",
            isChief
              ? "border-white/10 bg-white/[0.04] text-slate-300 hover:bg-white/[0.07] hover:text-white"
              : "border-stone-200 bg-white/70 text-stone-600 hover:bg-white hover:text-stone-950",
          ].join(" ")}
        >
          {customizing ? <X className="h-3.5 w-3.5" /> : <Settings2 className="h-3.5 w-3.5" />}
          {customizing ? "Done" : "Customize"}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 px-1">
        <span className={isChief ? "mr-1 text-[11px] text-slate-600" : "mr-1 text-[11px] text-stone-400"}>
          Open from Chat V2
        </span>
        {quickLinks.map((link) => (
          <a
            key={link.href}
            href={link.href}
            className={[
              "rounded-full border px-2.5 py-1 text-[11px] font-medium transition active:scale-[0.98]",
              isChief
                ? "border-white/10 bg-white/[0.035] text-slate-400 hover:bg-white/[0.07] hover:text-white"
                : "border-stone-200 bg-white/55 text-stone-500 hover:bg-white hover:text-stone-950",
            ].join(" ")}
          >
            {link.label}
          </a>
        ))}
      </div>

      {customizing ? (
        <CustomizePanel
          mode={mode}
          cards={orderedCards}
          hiddenIds={hiddenIds}
          onToggle={(cardId) => toggleCard(mode, cardId)}
          onMove={(cardId, direction) => moveCard(mode, cardId, direction)}
          onReset={() => resetMode(mode)}
        />
      ) : null}

      {visibleCards.map((card) => {
        const Icon = card.icon;
        return (
          <PanelCard
            key={card.id}
            tone={isChief ? "chief" : "life"}
            icon={<Icon className="h-4 w-4" />}
            title={card.title}
          >
            {card.render(context, mode, { onPrompt })}
          </PanelCard>
        );
      })}

      {visibleCards.length === 0 && !customizing ? (
        <PanelCard
          tone={isChief ? "chief" : "life"}
          icon={<Settings2 className="h-4 w-4" />}
          title="A quiet desk"
        >
          <p>Every card is hidden right now. Open Customize to bring back the ones you want.</p>
        </PanelCard>
      ) : null}
    </div>
  );
}

function CustomizePanel({
  mode,
  cards,
  hiddenIds,
  onToggle,
  onMove,
  onReset,
}: {
  mode: AssistantMode;
  cards: WorkspaceCardDefinition[];
  hiddenIds: Set<WorkspaceCardId>;
  onToggle: (cardId: WorkspaceCardId) => void;
  onMove: (cardId: WorkspaceCardId, direction: -1 | 1) => void;
  onReset: () => void;
}) {
  const isChief = mode === "chief_of_staff";

  const rowButton = [
    "grid h-7 w-7 place-items-center rounded-full border transition active:scale-[0.96] disabled:cursor-not-allowed disabled:opacity-30",
    isChief
      ? "border-white/10 bg-white/[0.04] text-slate-300 hover:bg-white/[0.08] hover:text-white"
      : "border-stone-200 bg-white/70 text-stone-500 hover:bg-white hover:text-stone-950",
  ].join(" ");

  return (
    <div
      className={[
        "rounded-3xl border p-4 shadow-sm backdrop-blur",
        isChief
          ? "border-teal-200/15 bg-white/[0.045] text-slate-300"
          : "border-white/70 bg-white/52 text-stone-600",
      ].join(" ")}
    >
      <p
        className={[
          "mb-3 text-sm font-semibold",
          isChief ? "text-white" : "text-stone-950",
        ].join(" ")}
      >
        Choose your cards
      </p>

      <ul className="space-y-2">
        {cards.map((card, index) => {
          const hidden = hiddenIds.has(card.id);
          return (
            <li key={card.id} className="flex items-center gap-2">
              <span
                className={[
                  "flex-1 truncate text-sm",
                  hidden ? "opacity-50" : "",
                ].join(" ")}
              >
                {card.title}
              </span>
              <button
                type="button"
                onClick={() => onMove(card.id, -1)}
                disabled={index === 0}
                aria-label={`Move ${card.title} up`}
                className={rowButton}
              >
                <ChevronUp className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => onMove(card.id, 1)}
                disabled={index === cards.length - 1}
                aria-label={`Move ${card.title} down`}
                className={rowButton}
              >
                <ChevronDown className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => onToggle(card.id)}
                aria-label={hidden ? `Show ${card.title}` : `Hide ${card.title}`}
                className={rowButton}
              >
                {hidden ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
              </button>
            </li>
          );
        })}
      </ul>

      <button
        type="button"
        onClick={onReset}
        className={[
          "mt-4 inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition active:scale-[0.98]",
          isChief
            ? "border-white/10 bg-white/[0.04] text-slate-300 hover:bg-white/[0.08] hover:text-white"
            : "border-stone-200 bg-white/70 text-stone-600 hover:bg-white hover:text-stone-950",
        ].join(" ")}
      >
        <RotateCcw className="h-3.5 w-3.5" />
        Reset to defaults
      </button>
    </div>
  );
}

function PanelCard({
  tone,
  icon,
  title,
  children,
}: {
  tone: "life" | "chief";
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  const isChief = tone === "chief";

  return (
    <div
      className={[
        "rounded-3xl border p-4 shadow-sm backdrop-blur",
        isChief
          ? "border-white/10 bg-white/[0.045] text-slate-300"
          : "border-white/70 bg-white/52 text-stone-600",
      ].join(" ")}
    >
      <div className="mb-3 flex items-center gap-2">
        <span
          className={[
            "grid h-8 w-8 place-items-center rounded-full",
            isChief ? "bg-teal-200/[0.08] text-teal-100" : "bg-white/70 text-stone-500",
          ].join(" ")}
        >
          {icon}
        </span>
        <h2 className={isChief ? "font-semibold text-white" : "font-semibold text-stone-950"}>
          {title}
        </h2>
      </div>
      <div className="text-sm leading-6 [&_ul]:space-y-1 [&_li]:list-inside [&_li]:list-disc">
        {children}
      </div>
    </div>
  );
}
