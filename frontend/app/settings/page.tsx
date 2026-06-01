"use client";

import Link from "next/link";
import {ChevronRight, MessageSquare, Heart, Image, ShieldCheck} from "lucide-react";
import { BackgroundStyleSettings } from "@/components/ambient/background-style-settings";
import { BackToChatButton } from "@/components/settings/back-to-chat-button";

export default function SettingsPage() {
  return (
    <main className="min-h-dvh">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-5 sm:py-8 fade-up">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold text-fg mb-2 tracking-tighter">
              Settings
            </h1>
            <p className="text-base text-fg-muted">
              Personalize how your assistant works.
            </p>
          </div>
          <div className="shrink-0 pt-1">
            <BackToChatButton />
          </div>
        </div>

        <section className="mt-2">
          <h2 className="text-[10px] font-semibold uppercase tracking-wider text-fg-subtle mb-2 px-1">
            Personalization
          </h2>
          <div className="glass rounded-2xl divide-y divide-border">
            <SettingsRow
              href="/settings/companion"
              icon={<Heart className="h-4 w-4" />}
              title="Companion Mode"
              subtitle="Choose how your assistant behaves emotionally"
            />
            <SettingsRow
              href="/settings/style-profiles"
              icon={<MessageSquare className="h-4 w-4" />}
              title="Conversation Style Profiles"
              subtitle="Teach the assistant to adapt its communication style"
            />

<SettingsRow
  href="/settings/avatar-mode"
  icon={<Image className="h-4 w-4" />}
  title="AI Avatar Mode"
  subtitle="Set the assistant avatar image and animation style"
/>
            <SettingsRow
              href="/settings/security"
              icon={<ShieldCheck className="h-4 w-4" />}
              title="Security & Privacy"
              subtitle="Manage Memory PIN and Google Calendar connection"
            />
          </div>
        </section>

        <section className="mt-6">
          <h2 className="text-[10px] font-semibold uppercase tracking-wider text-fg-subtle mb-2 px-1">
            Appearance
          </h2>
          <BackgroundStyleSettings />
        </section>
      </div>
    </main>
  );
}

function SettingsRow({
  href,
  icon,
  title,
  subtitle,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  subtitle: string;
}) {
  return (
    <Link
      href={href}
      className="flex items-center gap-3 px-4 py-3.5 hover:bg-fg/5 transition-colors"
    >
      <span className="text-fg-muted">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-fg font-medium">{title}</p>
        <p className="text-xs text-fg-muted truncate">{subtitle}</p>
      </div>
      <ChevronRight className="h-4 w-4 text-fg-subtle" />
    </Link>
  );
}
