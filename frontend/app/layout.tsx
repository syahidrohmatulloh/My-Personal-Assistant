import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Providers from "./providers";
import { AmbientBackground } from "@/components/ambient/ambient-background";
import { CursorReactiveGlow } from "@/components/ambient/cursor-reactive-glow";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "My Assistant",
  description: "Personal AI assistant",
};

export const viewport: Viewport = {
  // viewportFit=cover lets us use env(safe-area-inset-*) for the notch
  // and home indicator. maximumScale=1 stops iOS Safari zooming inputs on focus.
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fafaf7" },
    { media: "(prefers-color-scheme: dark)", color: "#080c14" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="font-sans antialiased">
        <AmbientBackground />
          <CursorReactiveGlow />
        <div className="relative z-[1]">
          <Providers>{children}</Providers>
        </div>
      </body>
    </html>
  );
}
