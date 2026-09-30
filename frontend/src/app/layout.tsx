import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/contexts/AuthContext";
import AppBackground from "@/components/AppBackground";

export const metadata: Metadata = {
  title: "AutoRef — AI-Powered Job Outreach",
  description: "Automate your job referral outreach with AI-generated emails, smart follow-ups, and centralized tracking.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <AppBackground />
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
