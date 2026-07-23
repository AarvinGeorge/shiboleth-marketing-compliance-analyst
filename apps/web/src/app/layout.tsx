// meta: root layout. Fonts per DESIGN.md typography: Inter (all UI),
// JetBrains Mono (evidence quotes + rule ids). Mounts the client Providers
// (TanStack Query + tooltips) and the U1 app shell (fixed left sidebar,
// expanded only); the main panel renders the active surface. Desktop 1440.
import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Providers } from "@/components/providers";
import { AppSidebar } from "@/components/shell/app-sidebar";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Adlign",
  description: "Marketing compliance monitoring",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${jetbrainsMono.variable} antialiased`}>
        <Providers>
          <div className="flex min-h-screen">
            <AppSidebar />
            <div className="min-w-0 flex-1">{children}</div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
