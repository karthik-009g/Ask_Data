import "./globals.css";
import { ReactNode } from "react";
import { Orbitron, Rajdhani, Space_Grotesk } from "next/font/google";

const orbitron = Orbitron({ subsets: ["latin"], weight: ["500", "600", "700", "800"], variable: "--font-orbitron" });
const rajdhani = Rajdhani({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-rajdhani" });
const space = Space_Grotesk({ subsets: ["latin"], variable: "--font-space" });

export const metadata = {
  title: "Ask Data",
  description: "AI-powered analytics workspace",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className={`${orbitron.variable} ${rajdhani.variable} ${space.variable} neon-theme`}>{children}</body>
    </html>
  );
}
