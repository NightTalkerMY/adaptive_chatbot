import "./globals.css";

export const metadata = {
  title: "Adaptive Chat",
  description:
    "A streaming Gemini chat whose UI adapts to what you're talking about",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" data-theme="general">
      <body>{children}</body>
    </html>
  );
}
