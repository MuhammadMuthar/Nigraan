import type { Metadata, Viewport } from "next";
import { AuthProvider } from "@/lib/auth";
import { THEME_BOOT_SCRIPT } from "@/lib/theme-script";
import { PreferencesSync } from "@/lib/preferences";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PreferencesFab, ThemedToaster } from "@/components/app/preferences-fab";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nigraan · finance control tower",
  description: "Checks every rupee going out, and tells you whether what's coming in will cover it.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F7F9FC" },
    { media: "(prefers-color-scheme: dark)", color: "#0A111D" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // the boot script sets the theme class before React hydrates
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body className="min-h-full font-sans">
        <PreferencesSync />
        <AuthProvider>
          <TooltipProvider>
            {children}
            <PreferencesFab />
          </TooltipProvider>
        </AuthProvider>
        <ThemedToaster />
      </body>
    </html>
  );
}
