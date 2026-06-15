import type { ComponentType, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function AppPageShell({
  eyebrow,
  title,
  description,
  actions,
  stats,
  children,
  maxWidthClassName = "max-w-6xl",
  className,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  stats?: ReactNode;
  children: ReactNode;
  maxWidthClassName?: string;
  className?: string;
}) {
  return (
    <main
      className={cn(
        "relative min-h-dvh overflow-hidden bg-[#f7f3ea] px-4 py-5 text-stone-950 sm:px-6 lg:px-8",
        className,
      )}
    >
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_16%_12%,rgba(251,191,36,0.14),transparent_24rem),radial-gradient(circle_at_82%_18%,rgba(45,212,191,0.12),transparent_28rem),radial-gradient(circle_at_76%_88%,rgba(244,114,182,0.10),transparent_26rem)]" />
        <div className="absolute inset-x-0 top-0 h-px bg-white/70" />
        <div className="absolute inset-0 opacity-[0.035] [background-image:linear-gradient(rgba(120,113,108,0.35)_1px,transparent_1px),linear-gradient(90deg,rgba(120,113,108,0.28)_1px,transparent_1px)] [background-size:44px_44px]" />
      </div>

      <div className={cn("relative z-10 mx-auto w-full", maxWidthClassName)}>
        <header className="mb-6 rounded-[2rem] border border-white/70 bg-white/45 p-4 shadow-sm shadow-stone-200/40 backdrop-blur sm:p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              {eyebrow ? (
                <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.24em] text-stone-400">
                  {eyebrow}
                </p>
              ) : null}

              <h1 className="text-3xl font-semibold tracking-[-0.04em] text-stone-950 sm:text-4xl">
                {title}
              </h1>

              {description ? (
                <p className="mt-3 max-w-2xl text-sm leading-6 text-stone-600">
                  {description}
                </p>
              ) : null}
            </div>

            {actions ? (
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                {actions}
              </div>
            ) : null}
          </div>
        </header>

        {stats ? <div className="mb-4">{stats}</div> : null}

        <div className="grid gap-4 pb-8">{children}</div>
      </div>
    </main>
  );
}

export function AppPanel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "rounded-[2rem] border border-white/70 bg-white/52 p-4 shadow-sm shadow-stone-200/35 backdrop-blur sm:p-5",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function AppStatGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={cn("grid gap-3 sm:grid-cols-2 lg:grid-cols-3", className)}>{children}</section>;
}

export function AppStatCard({
  label,
  value,
  hint,
  icon: Icon,
  children,
  className,
}: {
  label?: ReactNode;
  value?: ReactNode;
  hint?: ReactNode;
  icon?: ComponentType<{ className?: string }>;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-[1.5rem] border border-white/70 bg-white/48 p-4 shadow-sm shadow-stone-200/30 backdrop-blur",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {label ? (
            <p className="text-[11px] font-bold uppercase tracking-[0.20em] text-stone-400">{label}</p>
          ) : null}
          {value !== undefined ? (
            <p className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-stone-950">{value}</p>
          ) : null}
        </div>

        {Icon ? (
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-white/70 text-stone-500">
            <Icon className="h-4 w-4" />
          </span>
        ) : null}
      </div>
      {hint ? <p className="mt-1 text-xs leading-5 text-stone-500">{hint}</p> : null}
      {children}
    </div>
  );
}

export function AppHeaderAction({
  children,
  className,
  icon,
  variant = "secondary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  icon?: ReactNode;
  variant?: "primary" | "secondary" | "ghost" | string;
}) {
  const isPrimary = variant === "primary";
  const isGhost = variant === "ghost";

  return (
    <button
      type={props.type || "button"}
      {...props}
      className={cn(
        "inline-flex min-h-10 items-center justify-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold shadow-sm backdrop-blur transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60",
        isPrimary
          ? "border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100"
          : isGhost
            ? "border-transparent bg-transparent text-stone-600 hover:bg-white/55 hover:text-stone-950"
            : "border-stone-200 bg-white/70 text-stone-700 hover:bg-white hover:text-stone-950",
        className,
      )}
    >
      {icon}
      {children}
    </button>
  );
}

export function AppToolbar({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      {children}
    </div>
  );
}
