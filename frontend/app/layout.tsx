import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Adaptive Chat",
  description:
    "A streaming Gemini chat whose UI adapts to what you're talking about",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-theme="general">
      <body>{children}</body>
    </html>
  );
}
