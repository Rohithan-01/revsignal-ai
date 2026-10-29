import type { Metadata } from "next";
import { AppShell } from "@/components/app-shell";
import { RevenueDataProvider } from "@/components/data-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "RevSignal — Revenue Intelligence",
  description: "Explainable deal risk analysis and next-best actions for revenue teams.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <RevenueDataProvider>
          <AppShell>{children}</AppShell>
        </RevenueDataProvider>
      </body>
    </html>
  );
}
