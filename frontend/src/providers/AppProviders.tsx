"use client";

import type { ReactNode } from "react";
import { AccessRestrictedGate } from "@/components/auth/AccessRestrictedGate";
import { AuthProvider } from "@/contexts/AuthContext";
import { I18nProvider } from "@/contexts/I18nContext";

/** Composite provider tree for browser-wide concerns. */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <I18nProvider>
      <AuthProvider>
        <AccessRestrictedGate>{children}</AccessRestrictedGate>
      </AuthProvider>
    </I18nProvider>
  );
}
