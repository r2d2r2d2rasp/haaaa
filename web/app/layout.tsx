import type { Metadata } from "next";
import { Space_Grotesk, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import Nav from "@/components/Nav";

const sans = Space_Grotesk({ variable: "--font-sans", subsets: ["latin"] });
const mono = JetBrains_Mono({ variable: "--font-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TorinoSegnala",
  description: "Segnalazioni urbane a Torino da cittadini e POD hardware connessi.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="it" className={`${sans.variable} ${mono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <Nav />
        <main className="flex-1 flex flex-col">{children}</main>
      </body>
    </html>
  );
}
