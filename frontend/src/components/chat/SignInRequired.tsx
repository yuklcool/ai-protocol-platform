"use client";

import Link from "next/link";
import { SignInButton } from "@/components/SignInButton";
import { useI18n } from "@/contexts/I18nContext";
import { translateChat } from "@/lib/i18n/chat";

interface SignInRequiredProps {
  /** Optional skill display name to personalise the headline copy. */
  skillName?: string;
}

/**
 * Sign-in gate panel. Stays on the chat URL so successful authentication
 * re-renders directly into the chat the user originally wanted.
 */
export function SignInRequired({ skillName }: SignInRequiredProps) {
  const { locale } = useI18n();
  const headline = skillName
    ? translateChat(locale, "signIn.openSkill", { skill: skillName })
    : translateChat(locale, "signIn.openChat");

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 px-6 text-center">
      <div className="max-w-md space-y-3">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
          {translateChat(locale, "signIn.required")}
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground md:text-3xl">
          {headline}
        </h1>
        <p className="text-sm text-muted-foreground">
          {translateChat(locale, "signIn.description")}
        </p>
      </div>
      <SignInButton />
      <Link
        href="/"
        className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground hover:text-foreground"
      >
        {translateChat(locale, "signIn.backHome")}
      </Link>
    </main>
  );
}
