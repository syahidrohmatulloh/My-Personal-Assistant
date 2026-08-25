"use client"

import type { ReactNode } from "react"

export function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-slate-300/55 bg-slate-50/[0.86] p-4 shadow-sm shadow-slate-900/5 dark:border-white/10 dark:bg-slate-950/[0.62]">
      <p className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-zinc-500">
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-white">{value}</p>
    </div>
  )
}

export function TabButton({
  active,
  label,
  onClick,
}: {
  active: boolean
  label: string
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={[
        "rounded-full px-4 py-2 text-sm transition",
        active
          ? "bg-slate-950 text-white dark:bg-white dark:text-zinc-950"
          : "text-slate-500 dark:text-zinc-400 hover:bg-slate-100 dark:bg-white/10 hover:text-slate-950 dark:text-white",
      ].join(" ")}
    >
      {label}
    </button>
  )
}
