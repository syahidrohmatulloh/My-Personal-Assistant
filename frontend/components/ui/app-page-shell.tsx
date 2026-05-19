import type { ReactNode } from "react"
import Link from "next/link"
import { RefreshCcw, type LucideIcon } from "lucide-react"

type AppPageShellProps = {
  eyebrow: string
  title: string
  description?: ReactNode
  children: ReactNode
  actions?: ReactNode
  stats?: ReactNode
  maxWidthClassName?: string
}

type AppHeaderActionProps = {
  href?: string
  onClick?: () => void
  disabled?: boolean
  children: ReactNode
  icon?: ReactNode
  variant?: "primary" | "secondary" | "danger"
  type?: "button" | "submit"
}

type AppStatCardProps = {
  label: string
  value: string | number
  icon?: LucideIcon
}

export function AppPageShell({
  eyebrow,
  title,
  description,
  children,
  actions,
  stats,
  maxWidthClassName = "max-w-7xl",
}: AppPageShellProps) {
  return (
    <main className="min-h-screen px-4 py-5 text-slate-950 dark:text-zinc-100 sm:px-6 sm:py-6 lg:px-8">
      <div className={`mx-auto flex ${maxWidthClassName} flex-col gap-5 sm:gap-6`}>
        <section className="rounded-[1.75rem] border border-slate-200/70 dark:border-white/10 bg-white/80 dark:bg-slate-950/70 p-5 shadow-2xl shadow-slate-900/10 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.04] dark:shadow-black/30 sm:rounded-[2rem] sm:p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <p className="text-xs font-medium uppercase tracking-[0.28em] text-cyan-700 dark:text-cyan-300/80 sm:text-sm">
                {eyebrow}
              </p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 dark:text-white sm:text-4xl">
                {title}
              </h1>
              {description ? (
                <div className="mt-3 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300 dark:text-zinc-300">
                  {description}
                </div>
              ) : null}
            </div>

            {actions ? (
              <div className="flex flex-wrap gap-2 sm:gap-3 lg:justify-end">
                {actions}
              </div>
            ) : null}
          </div>

          {stats ? <div className="mt-6">{stats}</div> : null}
        </section>

        {children}
      </div>
    </main>
  )
}

export function AppHeaderAction({
  href,
  onClick,
  disabled,
  children,
  icon,
  variant = "secondary",
  type = "button",
}: AppHeaderActionProps) {
  const className = [
    "inline-flex min-h-10 items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-60",
    "w-full sm:w-auto",
    variant === "primary"
      ? "bg-cyan-400 text-slate-950 shadow-lg shadow-cyan-500/20 hover:bg-cyan-300"
      : variant === "danger"
        ? "border border-red-400/40 bg-red-50 text-red-700 hover:bg-red-100 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-200 dark:hover:bg-red-500/20"
        : "border border-slate-200/70 dark:border-white/10 bg-white/65 text-slate-700 dark:text-slate-200 shadow-sm shadow-slate-900/5 hover:bg-white dark:border-white/10 dark:bg-white/[0.04] dark:text-zinc-200 dark:hover:bg-white/10",
  ].join(" ")

  if (href) {
    return (
      <Link href={href} className={className}>
        {icon}
        {children}
      </Link>
    )
  }

  return (
    <button type={type} onClick={onClick} disabled={disabled} className={className}>
      {icon}
      {children}
    </button>
  )
}

export function AppStatGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-3 sm:grid-cols-3">{children}</div>
}

export function AppStatCard({ label, value, icon: Icon }: AppStatCardProps) {
  return (
    <div className="rounded-2xl border border-slate-200/70 dark:border-white/10 bg-white/75 p-4 shadow-sm shadow-slate-900/5 dark:border-white/10 dark:bg-black/20">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400 dark:text-zinc-500">
          {label}
        </p>
        {Icon ? <Icon className="h-4 w-4 text-cyan-600 dark:text-cyan-300" /> : null}
      </div>
      <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-white">
        {value}
      </p>
    </div>
  )
}

export function AppToolbar({ children }: { children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3 rounded-[1.5rem] border border-slate-200/70 dark:border-white/10 bg-white/70 dark:bg-slate-950/60 p-4 shadow-xl shadow-slate-900/5 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.035] md:flex-row md:items-center md:justify-between">
      {children}
    </section>
  )
}

export function AppPanel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`overflow-hidden rounded-[1.5rem] border border-slate-200/70 dark:border-white/10 bg-white/70 dark:bg-slate-950/60 shadow-xl shadow-slate-900/5 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.035] ${className}`}>
      {children}
    </section>
  )
}

export function RefreshIcon({ loading }: { loading?: boolean }) {
  return <RefreshCcw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
}
