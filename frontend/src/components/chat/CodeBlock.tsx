// CodeBlock — a fenced code block in a chat reply, with a copy affordance.

"use client";

import { useState, type ReactNode } from "react";
import { Check, Copy } from "lucide-react";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

interface HastNode {
  type?: string;
  tagName?: string;
  value?: string;
  properties?: { className?: unknown };
  children?: HastNode[];
}

export function hastText(node: unknown): string {
  const n = node as HastNode | undefined;
  if (!n || typeof n !== "object") return "";
  if (n.type === "text") return n.value ?? "";
  if (!Array.isArray(n.children)) return "";
  return n.children.map(hastText).join("");
}

export function hastLanguage(node: unknown): string {
  const n = node as HastNode | undefined;
  const code = n?.children?.find((c) => c.tagName === "code");
  const raw = code?.properties?.className;
  const classes = Array.isArray(raw) ? raw.map(String) : String(raw ?? "").split(/\s+/);
  const match = classes.find((c) => c.startsWith("language-"));
  return match ? match.slice("language-".length) : "";
}

type CopyState = "idle" | "copied" | "failed";

function CopyCodeButton({ text }: { text: string }) {
  const [state, setState] = useState<CopyState>("idle");
  const { locale } = useI18n();

  async function copy() {
    try {
      if (!navigator.clipboard) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(text.replace(/\n+$/, ""));
      setState("copied");
    } catch {
      setState("failed");
    }
    setTimeout(() => setState("idle"), 2000);
  }

  const title =
    state === "failed"
      ? translateChat(locale, "code.copyFailedTitle")
      : translateChat(locale, "code.copyTitle");
  const label =
    state === "copied"
      ? translateChat(locale, "code.copied")
      : state === "failed"
        ? translateChat(locale, "code.copyFailed")
        : translateChat(locale, "code.copy");

  return (
    <button
      type="button"
      onClick={copy}
      data-testid="code-copy"
      className="inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
      title={title}
      aria-label={translateChat(locale, "code.copyAria")}
    >
      {state === "copied" ? (
        <Check className="h-3 w-3" aria-hidden />
      ) : (
        <Copy className="h-3 w-3" aria-hidden />
      )}
      {label}
    </button>
  );
}

export function CodeBlock({
  text,
  language,
  children,
  actions,
}: {
  text: string;
  language?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  const { locale } = useI18n();
  if (!text.trim()) {
    return (
      <pre className="mb-2 overflow-x-auto rounded border border-border bg-muted p-3 text-xs">{children}</pre>
    );
  }

  return (
    <div className="mb-2 overflow-hidden rounded border border-border">
      <div className="flex items-center justify-between gap-2 border-b border-border bg-muted/60 px-2 py-1">
        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {language || translateChat(locale, "code.fallbackLanguage")}
        </span>
        <span className="flex items-center gap-1">
          {actions}
          <CopyCodeButton text={text} />
        </span>
      </div>
      <pre className="overflow-x-auto bg-muted p-3 text-xs">{children}</pre>
    </div>
  );
}
