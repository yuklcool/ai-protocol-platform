import type { Metadata } from "next";
import type { CSSProperties, ReactNode } from "react";
import { LocalModeBanner } from "@/components/LocalModeBanner";
import { BRANDING } from "@/lib/branding";
import { DEFAULT_LOCALE } from "@/lib/i18n";
import { AppProviders } from "@/providers/AppProviders";
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
    <html lang={DEFAULT_LOCALE}>
      <body
        className="font-sans bg-background text-foreground h-screen flex flex-col antialiased"
        style={brandThemeStyle}
      >
        <AppProviders>
          <LocalModeBanner />
          <div className="flex min-h-0 flex-1 flex-col">{children}</div>
        </AppProviders>
      </body>
    </html>
  );
}
