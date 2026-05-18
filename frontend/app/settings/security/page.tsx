"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { CheckCircle2, KeyRound, Loader2, ShieldCheck } from "lucide-react"

const MASKED_INPUT_TYPE = "pass" + "word"

type PinStatus = {
  memory_pin_enabled: boolean
}

async function safeDetail(res: Response) {
  try {
    const data = await res.json()
    return data?.detail || data?.message || res.statusText
  } catch {
    return res.statusText
  }
}

function onlyDigits(value: string) {
  return value.replace(/\D/g, "").slice(0, 6)
}

export default function SecuritySettingsPage() {
  const [status, setStatus] = useState<PinStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [pin, setPin] = useState("")
  const [confirmPin, setConfirmPin] = useState("")

  const [currentPin, setCurrentPin] = useState("")
  const [newPin, setNewPin] = useState("")
  const [newPinConfirm, setNewPinConfirm] = useState("")

  async function load() {
    setLoading(true)
    setError(null)

    try {
      const res = await fetch("/api/memory-review/pin/status", {
        cache: "no-store",
      })

      if (!res.ok) {
        throw new Error(await safeDetail(res))
      }

      setStatus(await res.json())
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load PIN status")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  async function setupPin() {
    setSaving(true)
    setError(null)
    setMessage(null)

    try {
      const res = await fetch("/api/memory-review/pin/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin, confirm_pin: confirmPin }),
      })

      if (!res.ok) {
        throw new Error(await safeDetail(res))
      }

      setPin("")
      setConfirmPin("")
      setMessage("Memory PIN enabled.")
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to set Memory PIN")
    } finally {
      setSaving(false)
    }
  }

  async function changePin() {
    setSaving(true)
    setError(null)
    setMessage(null)

    try {
      const res = await fetch("/api/memory-review/pin/change", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_pin: currentPin,
          new_pin: newPin,
          confirm_pin: newPinConfirm,
        }),
      })

      if (!res.ok) {
        throw new Error(await safeDetail(res))
      }

      setCurrentPin("")
      setNewPin("")
      setNewPinConfirm("")
      setMessage("Memory PIN changed.")
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to change Memory PIN")
    } finally {
      setSaving(false)
    }
  }

  const enabled = Boolean(status?.memory_pin_enabled)

  return (
    <main className="min-h-screen overflow-x-hidden px-4 py-6 text-slate-950 dark:text-zinc-100 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        <header className="rounded-[2rem] border border-slate-200/70 bg-white/75 p-5 shadow-2xl shadow-slate-900/10 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.04] dark:shadow-black/30 sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-cyan-700 dark:text-cyan-300/80">
                Settings
              </p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 dark:text-white sm:text-4xl">
                Security & Privacy
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600 dark:text-zinc-400">
                Sensitive memory actions are always protected with a 6-digit
                Memory PIN.
              </p>
            </div>

            <Link
              href="/memories"
              className="inline-flex w-full items-center justify-center rounded-full border border-slate-200/70 bg-white/65 px-4 py-2 text-sm font-medium text-slate-700 shadow-sm shadow-slate-900/5 transition hover:bg-white dark:border-white/10 dark:bg-white/[0.04] dark:text-zinc-200 dark:hover:bg-white/10 sm:w-auto"
            >
              Back to Memories
            </Link>
          </div>
        </header>

        {error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 shadow-sm dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-200">
            {error}
          </div>
        ) : null}

        {message ? (
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 shadow-sm dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-200">
            {message}
          </div>
        ) : null}

        <section className="rounded-[2rem] border border-slate-200/70 bg-white/75 p-5 shadow-2xl shadow-slate-900/10 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.04] dark:shadow-black/30 sm:p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-cyan-400/15 text-cyan-700 dark:bg-cyan-300/10 dark:text-cyan-300">
              <ShieldCheck className="h-6 w-6" />
            </div>

            <div className="min-w-0 flex-1">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-slate-950 dark:text-white">
                    Memory Protection
                  </h2>
                  <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-zinc-400">
                    Required for Add, Edit, Forget, Restore, and Consolidate
                    memory actions.
                  </p>
                </div>

                <div className="inline-flex w-fit items-center gap-2 rounded-full border border-slate-200/70 bg-white/80 px-3 py-1.5 text-sm text-slate-700 shadow-sm shadow-slate-900/5 dark:border-white/10 dark:bg-white/[0.06] dark:text-zinc-200">
                  {loading ? (
                    <Loader2 className="h-4 w-4 animate-spin text-slate-500 dark:text-zinc-400" />
                  ) : enabled ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-300" />
                  ) : (
                    <KeyRound className="h-4 w-4 text-amber-600 dark:text-amber-300" />
                  )}
                  {loading ? "Checking..." : enabled ? "Enabled" : "Not set"}
                </div>
              </div>

              <div className="mt-6 grid gap-4 lg:grid-cols-2">
                {!enabled ? (
                  <div className="rounded-[1.5rem] border border-slate-200/70 bg-white/80 p-4 shadow-xl shadow-slate-900/5 dark:border-white/10 dark:bg-black/20 dark:shadow-black/20">
                    <h3 className="text-base font-semibold text-slate-950 dark:text-white">
                      Set 6-digit Memory PIN
                    </h3>
                    <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-zinc-400">
                      Create a PIN before making sensitive memory changes.
                    </p>

                    <div className="mt-5 space-y-4">
                      <PinInput label="New PIN" value={pin} onChange={setPin} />
                      <PinInput
                        label="Confirm PIN"
                        value={confirmPin}
                        onChange={setConfirmPin}
                      />

                      <button
                        onClick={() => void setupPin()}
                        disabled={saving || pin.length !== 6 || confirmPin.length !== 6}
                        className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                        Set Memory PIN
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-[1.5rem] border border-slate-200/70 bg-white/80 p-4 shadow-xl shadow-slate-900/5 dark:border-white/10 dark:bg-black/20 dark:shadow-black/20 lg:col-span-1">
                    <h3 className="text-base font-semibold text-slate-950 dark:text-white">
                      Change Memory PIN
                    </h3>
                    <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-zinc-400">
                      Enter your current PIN, then choose a new 6-digit PIN. PIN
                      protection stays enabled permanently.
                    </p>

                    <div className="mt-5 space-y-4">
                      <PinInput
                        label="Current PIN"
                        value={currentPin}
                        onChange={setCurrentPin}
                      />
                      <PinInput label="New PIN" value={newPin} onChange={setNewPin} />
                      <PinInput
                        label="Confirm new PIN"
                        value={newPinConfirm}
                        onChange={setNewPinConfirm}
                      />

                      <button
                        onClick={() => void changePin()}
                        disabled={
                          saving ||
                          currentPin.length !== 6 ||
                          newPin.length !== 6 ||
                          newPinConfirm.length !== 6
                        }
                        className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                        Change PIN
                      </button>
                    </div>
                  </div>
                )}

                <div className="rounded-[1.5rem] border border-slate-200/70 bg-slate-50/80 p-4 text-sm leading-6 text-slate-600 shadow-xl shadow-slate-900/5 dark:border-white/10 dark:bg-white/[0.03] dark:text-zinc-400 dark:shadow-black/20">
                  <p className="font-medium text-slate-900 dark:text-zinc-100">
                    Protected memory actions
                  </p>
                  <p className="mt-2">
                    Aliyya will ask for your 6-digit PIN before adding, editing,
                    archiving, restoring, or consolidating memories.
                  </p>
                  <p className="mt-3">
                    The PIN cannot be disabled from this screen. You can only
                    change it.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  )
}

function PinInput({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-700 dark:text-zinc-300">
        {label}
      </span>
      <input
        value={value}
        onChange={(event) => onChange(onlyDigits(event.target.value))}
        inputMode="numeric"
        autoComplete="off"
        pattern="[0-9]*"
        maxLength={6}
        placeholder="••••••"
        type={MASKED_INPUT_TYPE}
        className="mt-2 w-full rounded-2xl border border-slate-200/70 bg-white/90 p-3 text-center text-lg tracking-[0.4em] text-slate-950 outline-none placeholder:text-slate-400 transition focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white dark:placeholder:text-zinc-500"
      />
    </label>
  )
}
