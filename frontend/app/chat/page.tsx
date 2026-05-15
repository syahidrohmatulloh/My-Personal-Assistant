import { Sparkles } from "lucide-react";

export default function ChatIndexPage() {
  return (
    <main className="flex-1 grid place-items-center px-6">
      <div className="text-center max-w-md fade-up">
        <div className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-accent shadow-xl shadow-accent/30 mb-5">
          <Sparkles className="h-6 w-6 text-on-accent" strokeWidth={2.2} />
        </div>
        <h1 className="text-2xl sm:text-3xl font-semibold text-fg mb-2 tracking-tighter">
          Start a conversation
        </h1>
        <p className="text-sm sm:text-base text-fg-muted">
          Tap <span className="text-fg font-medium">New chat</span> to begin.
        </p>
      </div>
    </main>
  );
}
