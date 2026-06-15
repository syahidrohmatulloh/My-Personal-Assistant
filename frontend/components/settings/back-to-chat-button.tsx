"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { cn } from "@/lib/utils";

export function BackToChatButton({
  className,
  children = "Back to Chat V2",
}: {
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <Link
      href="/chat-v2"
      className={cn(
        "inline-flex min-h-10 items-center justify-center gap-2 rounded-full border border-stone-200 bg-white/70 px-4 py-2 text-sm font-semibold text-stone-700 shadow-sm backdrop-blur transition hover:bg-white hover:text-stone-950 active:scale-[0.98]",
        className,
      )}
    >
      <ArrowLeft className="h-4 w-4" />
      {children}
    </Link>
  );
}
