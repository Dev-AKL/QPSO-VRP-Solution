import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

// Shadcn standard typography foundation
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "QPSO Dispatch Platform",
  description: "Enterprise Route Optimizer",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark" style={{ colorScheme: "dark" }}>
      <body className={`font-sans antialiased bg-background text-foreground ${inter.variable}`}>
        {children}
      </body>
    </html>
  );
}