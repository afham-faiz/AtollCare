import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";

import { APP_NAME, APP_TAGLINE } from "@/app/config";
import "@/styles/globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: APP_NAME, template: `%s · ${APP_NAME}` },
  description: APP_TAGLINE,
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0e7c86" };

// F-M10.4 apply the stored theme before first paint (system default otherwise).
const THEME_SCRIPT = `try{var t=localStorage.getItem("atollcare.theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export default function ({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} h-full`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
