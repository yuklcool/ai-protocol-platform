import type { Metadata } from "next";
import type { CSSProperties, ReactNode } from "react";
import { LocalModeBanner } from "@/components/LocalModeBanner";
import { ConsoleFrame } from "@/components/navigation/ConsoleFrame";
import { BRANDING } from "@/lib/branding";
import { DEFAULT_LOCALE } from "@/lib/i18n";
import { AppProviders } from "@/providers/AppProviders";
import "./fonts.css";
import "./globals.css";

export const metadata: Metadata = {
  title: BRANDING.appName,
  description: BRANDING.description,
  icons: {
    icon: BRANDING.logo.favicon,
  },
};

const brandThemeStyle = {
  "--primary": BRANDING.theme.primaryHsl,
  "--primary-foreground": BRANDING.theme.primaryForegroundHsl,
  "--ring": BRANDING.theme.primaryHsl,
} as CSSProperties;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang={DEFAULT_LOCALE} style={brandThemeStyle}>
      <body
        className="font-sans text-foreground h-dvh flex flex-col antialiased"
      >
        <div className="app-backdrop" aria-hidden="true"></div>
        <AppProviders>
          <LocalModeBanner />
          <div className="flex min-h-0 flex-1 flex-col">
            <ConsoleFrame>{children}</ConsoleFrame>
          </div>
        </AppProviders>
      </body>
    </html>
  );
}
