import "../globals.css";
import { AuthProvider } from "../contexts/AuthContext";
import { LanguageProvider } from "../contexts/LanguageContext";
import Navbar from "../components/Navbar";
import CookieConsent from "../components/CookieConsent";

const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://museforge.ai";

export const metadata = {
  metadataBase: new URL(BASE_URL),
  title: {
    default: "MuseForge — Agentic AI Video Studio",
    template: "%s | MuseForge",
  },
  description:
    "Turn your ideas into cinematic videos with AI. Generate stunning micro-dramas with a multi-agent AI pipeline in minutes.",
  keywords: [
    "AI video generation",
    "artificial intelligence video",
    "cinematic video",
    "MuseForge",
    "agentic AI",
    "video studio",
    "AI filmmaking",
    "text to video",
  ],
  authors: [{ name: "MuseForge", url: BASE_URL }],
  creator: "MuseForge",
  openGraph: {
    type: "website",
    locale: "en_US",
    url: BASE_URL,
    siteName: "MuseForge",
    title: "MuseForge — Agentic AI Video Studio",
    description:
      "Turn your ideas into cinematic videos with AI. Generate stunning micro-dramas with a multi-agent AI pipeline in minutes.",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "MuseForge — AI Video Studio",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "MuseForge — Agentic AI Video Studio",
    description: "Turn your ideas into cinematic videos with AI.",
    images: ["/og-image.png"],
    creator: "@museforge_ai",
    site: "@museforge_ai",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  icons: {
    icon: "/favicon.ico",
    shortcut: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" dir="ltr">
      <body className="antialiased min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
        <AuthProvider>
          <LanguageProvider>
            <Navbar />
            {children}
            <CookieConsent />
          </LanguageProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
