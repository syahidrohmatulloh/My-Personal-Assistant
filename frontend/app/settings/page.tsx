"use client";

import Link from "next/link";
import { ArrowLeft, ChevronRight, MessageSquare } from "lucide-react";
import { BackgroundStyleSettings } from "@/components/ambient/background-style-settings";
import { BackToChatButton } from "@/components/settings/back-to-chat-button";

export default function SettingsPage() {
  return (
    <main className="min-h-dvh">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-5 sm:py-8 fade-up">
        <BackToChatButton />

        <h1 className="text-3xl font-semibold text-fg mb-2 tracking-tighter">
          Settings
        </h1>
        <p className="text-base text-fg-muted mb-6">
          Personalize how your assistant works.
        </p>

        <section className="mt-2">
          <h2 className="text-[10px] font-semibold uppercase tracking-wider text-fg-subtle mb-2 px-1">
            Personalization
          </h2>
          <div className="glass rounded-2xl divide-y divide-border">
            <SettingsRow
              href="/settings/style-profiles"
              icon={<MessageSquare className="h-4 w-4" />}
              title="Conversation Style Profiles"
              subtitle="Teach the assistant to adapt its communication style"
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
