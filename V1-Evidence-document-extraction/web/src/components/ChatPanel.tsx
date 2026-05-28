"use client";

import { ArrowUp, ShieldCheck } from "lucide-react";
import type { FormEvent } from "react";
import { useMemo, useState, useTransition } from "react";
import type { ChatMessage, ChatMessageCreateResult, WorkspaceActionResult } from "@/lib/workspace-types";

type ChatPanelProps = {
  activeCaseId: string | null;
  messages: ChatMessage[];
  onSendMessage: (content: string, threadId?: string | null) => Promise<WorkspaceActionResult<ChatMessageCreateResult>>;
};

export function ChatPanel({ activeCaseId, messages, onSendMessage }: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const activeThreadId = useMemo(() => {
    const lastThreadMessage = [...messages].reverse().find((message) => message.threadId);
    return lastThreadMessage?.threadId ?? null;
  }, [messages]);
  const canSend = Boolean(activeCaseId && draft.trim() && !isPending);

  function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSend) {
      return;
    }
    const content = draft.trim();
    setError(null);
    startTransition(async () => {
      const result = await onSendMessage(content, activeThreadId);
      if (result.ok) {
        setDraft("");
      } else {
        setError(result.error);
      }
    });
  }

  const suggestions = [
    "Find cited authority for refusal to bargain.",
    "Check citation anchors for this matter.",
    "Draft a pack-bounded issue outline.",
  ];

  return (
    <section className="flex min-h-0 flex-1 flex-col bg-[#fcf9f5]" aria-label="Legal chat">
      <header className="flex min-h-12 shrink-0 items-center justify-between border-b border-[#c3c6d6] bg-[#fcf9f5]/90 px-4 py-2">
        <div className="min-w-0">
          <h1 className="truncate text-sm font-bold text-[#1c1c1a]">Legal research chat</h1>
          <p className="truncate text-xs text-[#434654]">Pack-bounded drafting and source review</p>
        </div>
        <div className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-[11px] font-bold text-emerald-800">
          <ShieldCheck size={14} />
          Cited pack only
        </div>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        {messages.length === 0 ? (
          <div className="mx-auto mt-16 max-w-md text-center">
            <h2 className="text-xl font-semibold text-[#1c1c1a]">Open a case to continue research</h2>
            <p className="mt-2 text-sm leading-6 text-[#434654]">
              Case facts, research packs, cited drafts, and review decisions appear here when a matter is loaded.
            </p>
          </div>
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-5">
            {messages.map((message) => (
              <article key={message.messageId} className={message.role === "user" ? "self-end" : "self-start"}>
                <div
                  className={`max-w-[720px] whitespace-pre-wrap rounded-xl px-4 py-3 text-xs leading-5 ${
                    message.role === "user"
                      ? "bg-[#003d9b] text-white"
                      : message.role === "tool"
                        ? "border border-[#c3c6d6] bg-[#f6f3ef] text-[#434654]"
                        : "border border-[#c3c6d6] bg-white text-[#1c1c1a]"
                  }`}
                >
                  {message.content}
                </div>
                {message.packId ? <p className="mt-1.5 text-[11px] text-[#434654]">Pack: {message.packId}</p> : null}
              </article>
            ))}
          </div>
        )}
      </div>
      <form className="shrink-0 border-t border-[#c3c6d6] bg-[#fcf9f5] p-4" onSubmit={submitMessage}>
        {error ? (
          <p className="mx-auto mb-3 max-w-3xl rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800" role="alert">
            {error}
          </p>
        ) : null}
        <div className="mx-auto mb-3 flex max-w-3xl flex-wrap gap-1.5">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              className="rounded-full border border-[#c3c6d6] bg-[#f0edea] px-2.5 py-1 text-[11px] font-medium text-[#434654] transition hover:border-[#003d9b] hover:bg-[#dae2ff] hover:text-[#003d9b]"
              type="button"
              onClick={() => setDraft(suggestion)}
              disabled={!activeCaseId || isPending}
            >
              {suggestion}
            </button>
          ))}
        </div>
        <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-xl border border-[#c3c6d6] bg-white p-2.5 shadow-sm focus-within:border-[#003d9b] focus-within:ring-2 focus-within:ring-[#003d9b]/10">
          <textarea
            className="max-h-28 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-xs leading-5 text-[#1c1c1a] outline-none placeholder:text-[#737685] disabled:text-[#737685]"
            aria-label="Message"
            rows={1}
            name="message"
            value={draft}
            disabled={!activeCaseId || isPending}
            placeholder={activeCaseId ? "Ask a pack-bounded legal research question" : "Open a matter to start chatting"}
            onChange={(event) => setDraft(event.target.value)}
          />
          <button
            type="submit"
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#003d9b] text-white transition hover:bg-[#0052cc] disabled:cursor-not-allowed disabled:bg-[#c3c6d6]"
            aria-label="Send message"
            disabled={!canSend}
          >
            <ArrowUp size={18} />
          </button>
        </div>
      </form>
    </section>
  );
}
