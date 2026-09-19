"use client";

import { useState, type FormEvent } from "react";

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

type AIChatSidebarProps = {
  messages: ChatMessage[];
  isLoading: boolean;
  errorMessage: string;
  onSendMessage: (message: string) => Promise<void>;
};

export const AIChatSidebar = ({
  messages,
  isLoading,
  errorMessage,
  onSendMessage,
}: AIChatSidebarProps) => {
  const [draft, setDraft] = useState("");

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = draft.trim();
    if (!trimmed || isLoading) {
      return;
    }
    setDraft("");
    await onSendMessage(trimmed);
  };

  return (
    <aside className="rounded-[28px] border border-[var(--stroke)] bg-white/90 p-6 shadow-[var(--shadow)] backdrop-blur">
      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-[var(--gray-text)]">
        AI Assistant
      </p>
      <h2 className="mt-3 font-display text-2xl font-semibold text-[var(--navy-dark)]">
        Ask and update
      </h2>
      <p className="mt-2 text-sm leading-6 text-[var(--gray-text)]">
        Ask questions about your board or request card updates in plain language.
      </p>

      <div className="mt-5 grid max-h-[420px] gap-3 overflow-y-auto rounded-2xl border border-[var(--stroke)] bg-[var(--surface)] p-4">
        {messages.map((message, index) => (
          <div
            key={`${message.role}-${index}`}
            className={`rounded-xl px-3 py-2 text-sm leading-6 ${
              message.role === "assistant"
                ? "bg-white text-[var(--navy-dark)]"
                : "bg-[var(--primary-blue)]/10 text-[var(--navy-dark)]"
            }`}
          >
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--gray-text)]">
              {message.role}
            </p>
            <p className="mt-1 whitespace-pre-wrap">{message.content}</p>
          </div>
        ))}
      </div>

      {errorMessage ? (
        <p className="mt-4 text-sm font-medium text-[var(--secondary-purple)]">{errorMessage}</p>
      ) : null}

      <form className="mt-4 grid gap-3" onSubmit={handleSubmit}>
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Example: Move QA micro-interactions to Done and summarize this sprint."
          className="min-h-[96px] rounded-xl border border-[var(--stroke)] bg-white px-3 py-2 text-sm text-[var(--navy-dark)] outline-none transition focus:border-[var(--primary-blue)]"
        />
        <button
          type="submit"
          disabled={isLoading}
          className="h-11 rounded-xl bg-[var(--secondary-purple)] px-4 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-70"
        >
          {isLoading ? "Thinking..." : "Send to AI"}
        </button>
      </form>
    </aside>
  );
};
