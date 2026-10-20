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
    <main className="flex min-h-screen flex-col items-center justify-center px-4 py-10 text-center sm:px-6">
      <div className="glass-panel empty-state flex w-full max-w-lg flex-col items-center gap-6 p-6 sm:p-10">
        <div className="space-y-4">
          <p className="badge inline-flex px-3 py-1 text-xs font-medium text-primary">
            {translateChat(locale, "signIn.required")}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground md:text-3xl">
            {headline}
          </h1>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {translateChat(locale, "signIn.description")}
          </p>
        </div>
        <SignInButton />
        <Link
          href="/"
          className="button-ghost inline-flex items-center px-3 py-2 text-sm"
        >
          {translateChat(locale, "signIn.backHome")}
        </Link>
      </div>
    </main>
  );
}
