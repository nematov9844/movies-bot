import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Movie Platform — Admin Panel",
  description: "Telegram Media Platform boshqaruv paneli",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="uz">
      <body>{children}</body>
    </html>
  );
}
