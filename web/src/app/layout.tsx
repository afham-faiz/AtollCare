import type { Metadata, Viewport } from "next";
import { Red_Hat_Display, Red_Hat_Mono, Red_Hat_Text } from "next/font/google";

import { APP_NAME, APP_TAGLINE } from "@/app/config";
import "@/styles/globals.css";

// one family, three cuts (variable weights): Display for headings and the big light numerals, Text for everything
// you read, Mono for codes
const display = Red_Hat_Display({ variable: "--font-display-face", subsets: ["latin"] });
const text = Red_Hat_Text({ variable: "--font-text", subsets: ["latin"] });
const mono = Red_Hat_Mono({ variable: "--font-mono-face", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: APP_NAME, template: `%s · ${APP_NAME}` },
  description: APP_TAGLINE,
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#e6ede9", viewportFit: "cover" };

export default function ({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${display.variable} ${text.variable} ${mono.variable} h-full`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
