"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2, RotateCcw, Save } from "lucide-react";

import { AssistantAvatar } from "@/components/avatar/AssistantAvatar";
import { useAssistantDisplayName } from "@/hooks/use-assistant-display-name";
import { useAvatarProfile, useDeleteAvatarProfile, useUpdateAvatarProfile } from "@/hooks/use-avatar-mode";
import type { AvatarAnimationStyle } from "@/lib/avatar-mode-api";

const CONSENT_COPY =
  "I confirm I have the right or permission to use this image as the assistant avatar.";

export default function AvatarModeSettingsPage() {
  const assistantName = useAssistantDisplayName();
  const { data: profile, isLoading } = useAvatarProfile();
  const updateMutation = useUpdateAvatarProfile();
  const deleteMutation = useDeleteAvatarProfile();

  const [imageUrl, setImageUrl] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [consent, setConsent] = useState(false);
  const [animationStyle, setAnimationStyle] = useState<AvatarAnimationStyle>("calm");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!profile) return;
    setImageUrl(profile.image_url ?? "");
    setEnabled(profile.avatar_mode_enabled);
    setConsent(profile.consent_confirmed);
    setAnimationStyle(profile.animation_style ?? "calm");
  }, [profile]);

  const resolvedAssistantName = assistantName || "Assistant";

  const previewProfile = useMemo(
    () => ({
      ...(profile ?? {
        image_url: null,
        avatar_mode_enabled: false,
        consent_confirmed: false,
        animation_style: "calm" as AvatarAnimationStyle,
      }),
      image_url: imageUrl.trim() || null,
      avatar_mode_enabled: enabled,
      consent_confirmed: consent,
      animation_style: animationStyle,
    }),
    [animationStyle, consent, enabled, imageUrl, profile],
  );

  async function save() {
    setMessage(null);
    try {
      await updateMutation.mutateAsync({
        image_url: imageUrl.trim() || null,
        avatar_mode_enabled: enabled,
        consent_confirmed: consent,
        animation_style: animationStyle,
      });
      setMessage("Avatar Mode saved.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save Avatar Mode.");
    }
  }

  async function reset() {
    setMessage(null);
    try {
      await deleteMutation.mutateAsync();
      setImageUrl("");
      setEnabled(false);
      setConsent(false);
      setAnimationStyle("calm");
      setMessage("Avatar Mode reset.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to reset Avatar Mode.");
    }
  }

  const busy = updateMutation.isPending || deleteMutation.isPending;

  return (
    <main className="min-h-dvh">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-5 sm:py-8 fade-up">
        <Link href="/settings" className="inline-flex items-center gap-2 text-sm text-fg-muted hover:text-fg mb-5">
          <ArrowLeft className="h-4 w-4" />
          Back to Settings
        </Link>

        <div className="flex items-start justify-between gap-4 mb-6">
          <div>
            <h1 className="text-3xl font-semibold text-fg tracking-tighter">AI Avatar Mode</h1>
            <p className="text-sm text-fg-muted mt-2 max-w-xl">
              Give {resolvedAssistantName} a calm visual presence. This version only stores and previews an approved
              avatar image; it does not clone faces or generate talking videos.
            </p>
          </div>
          <AssistantAvatar
            profile={previewProfile}
            assistantName={resolvedAssistantName}
            state={enabled ? "typing" : "disabled"}
            size="lg"
          />
        </div>

        <div className="glass rounded-2xl p-4 sm:p-5 space-y-5">
          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-fg-muted">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading avatar settings…
            </div>
          ) : (
            <>
              <label className="flex items-start justify-between gap-4">
                <span>
                  <span className="block text-sm font-medium text-fg">Enable AI Avatar Mode</span>
                  <span className="block text-xs text-fg-muted mt-1">Show an approved avatar for the assistant.</span>
                </span>
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(event) => setEnabled(event.target.checked)}
                  className="mt-1 h-4 w-4 accent-current"
                />
              </label>

              <label className="block space-y-2">
                <span className="text-sm font-medium text-fg">Avatar image URL</span>
                <input
                  value={imageUrl}
                  onChange={(event) => setImageUrl(event.target.value)}
                  placeholder="https://… or /avatar.png"
                  className="w-full rounded-xl border border-border bg-bg/70 px-3 py-2 text-sm text-fg outline-none focus:ring-2 focus:ring-accent/30"
                />
                <span className="block text-xs text-fg-muted">
                  Use your own image, an AI-generated character, or an image you have permission to use.
                </span>
              </label>

              <label className="block space-y-2">
                <span className="text-sm font-medium text-fg">Animation style</span>
                <select
                  value={animationStyle}
                  onChange={(event) => setAnimationStyle(event.target.value as AvatarAnimationStyle)}
                  className="w-full rounded-xl border border-border bg-bg/70 px-3 py-2 text-sm text-fg outline-none focus:ring-2 focus:ring-accent/30"
                >
                  <option value="calm">Calm</option>
                  <option value="subtle">Subtle</option>
                  <option value="minimal">Minimal</option>
                </select>
              </label>

              <label className="flex items-start gap-3 rounded-xl border border-border bg-fg/[0.03] p-3">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(event) => setConsent(event.target.checked)}
                  className="mt-0.5 h-4 w-4 accent-current"
                />
                <span className="text-xs text-fg-muted leading-relaxed">{CONSENT_COPY}</span>
              </label>

              {message ? <p className="text-xs text-fg-muted">{message}</p> : null}

              <div className="flex flex-col sm:flex-row gap-2 pt-1">
                <button
                  type="button"
                  onClick={save}
                  disabled={busy}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-medium text-on-accent disabled:opacity-50"
                >
                  {updateMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  Save Avatar Mode
                </button>
                <button
                  type="button"
                  onClick={reset}
                  disabled={busy}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-border px-4 py-2 text-sm font-medium text-fg-muted hover:text-fg disabled:opacity-50"
                >
                  {deleteMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                  Reset
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
