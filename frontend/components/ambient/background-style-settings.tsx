"use client";

import { useEffect, useState } from "react";
import {
  BACKGROUND_MODE_DESCRIPTIONS,
  BACKGROUND_MODE_LABELS,
  BACKGROUND_STYLE_DESCRIPTIONS,
  BACKGROUND_STYLE_LABELS,
  BACKGROUND_STYLES,
  type BackgroundIntensity,
  type BackgroundMode,
  type BackgroundSettings,
  DEFAULT_BACKGROUND_SETTINGS,
  readBackgroundMoodHint,
  readBackgroundSettings,
  saveBackgroundSettings,
} from "@/lib/ambient-background";
import { cn } from "@/lib/utils";

export function BackgroundStyleSettings() {
  const [settings, setSettings] = useState<BackgroundSettings>(DEFAULT_BACKGROUND_SETTINGS);

  useEffect(() => {
    setSettings(readBackgroundSettings());
  }, []);

  function update(next: Partial<BackgroundSettings>) {
    const merged = { ...settings, ...next };
    setSettings(merged);
    saveBackgroundSettings(merged);
  }

  const moodHint = typeof window === "undefined" ? null : readBackgroundMoodHint();

  return (
    <div className="glass rounded-2xl p-4 sm:p-5 space-y-5">
      <div>
        <h3 className="text-sm font-semibold text-fg">Background Style</h3>
        <p className="mt-1 text-xs leading-relaxed text-fg-muted">
          Add a subtle ambient visual layer behind the app. It is visual only and
          stays behind chat content.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {BACKGROUND_STYLES.map((style) => {
          const active = settings.style === style;
          return (
            <button
              key={style}
              type="button"
              onClick={() => update({ style })}
              className={cn(
                "text-left rounded-xl border px-3.5 py-3 transition-all",
                "hover:bg-fg/5 active:scale-[0.99]",
                active
                  ? "border-accent/45 bg-accent-soft/50 shadow-sm shadow-accent/10"
                  : "border-border bg-fg/[0.025]",
              )}
            >
              <span className="block text-sm font-medium text-fg">
                {BACKGROUND_STYLE_LABELS[style]}
              </span>
              <span className="mt-1 block text-xs leading-snug text-fg-muted">
                {BACKGROUND_STYLE_DESCRIPTIONS[style]}
              </span>
            </button>
          );
        })}
      </div>

      <FieldGroup label="Background Mode">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {(["manual", "mood-based"] as BackgroundMode[]).map((mode) => {
            const active = settings.mode === mode;
            return (
              <button
                key={mode}
                type="button"
                onClick={() => update({ mode })}
                disabled={settings.style === "off"}
                className={cn(
                  "rounded-xl border px-3.5 py-3 text-left transition-all",
                  "hover:bg-fg/5 active:scale-[0.99] disabled:opacity-45",
                  active
                    ? "border-accent/45 bg-accent-soft/50 shadow-sm shadow-accent/10"
                    : "border-border bg-fg/[0.025]",
                )}
              >
                <span className="block text-sm font-medium text-fg">
                  {BACKGROUND_MODE_LABELS[mode]}
                </span>
                <span className="mt-1 block text-xs leading-snug text-fg-muted">
                  {BACKGROUND_MODE_DESCRIPTIONS[mode]}
                </span>
              </button>
            );
          })}
        </div>
        {settings.mode === "mood-based" && moodHint && (
          <p className="mt-2 text-[11px] leading-relaxed text-fg-subtle">
            Current chat mood hint: {moodHint.mood} · palette {moodHint.palette}
          </p>
        )}
      </FieldGroup>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
        <FieldGroup label="Intensity">
          <SegmentedControl<BackgroundIntensity>
            value={settings.intensity}
            options={[
              { value: "low", label: "Low" },
              { value: "medium", label: "Medium" },
            ]}
            onChange={(intensity) => update({ intensity })}
            disabled={settings.style === "off"}
          />
        </FieldGroup>

        <FieldGroup label="Motion">
          <SegmentedControl<boolean>
            value={settings.motion}
            options={[
              { value: true, label: "Animated" },
              { value: false, label: "Static" },
            ]}
            onChange={(motion) => update({ motion })}
            disabled={settings.style === "off"}
          />
        </FieldGroup>
      </div>

      <p className="text-[11px] leading-relaxed text-fg-subtle">
        Motion automatically reduces if your device has prefers-reduced-motion
        enabled.
      </p>
    </div>
  );
}

function FieldGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-fg-subtle">
        {label}
      </p>
      {children}
    </div>
  );
}

function SegmentedControl<T extends string | boolean>({
  value,
  options,
  onChange,
  disabled,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  disabled?: boolean;
}) {
  return (
    <div
      className={cn(
        "inline-flex w-full rounded-xl border border-border bg-fg/[0.035] p-1",
        disabled && "opacity-45",
      )}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={String(option.value)}
            type="button"
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={cn(
              "flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-all",
              active
                ? "bg-fg/10 text-fg shadow-sm"
                : "text-fg-muted hover:text-fg",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
