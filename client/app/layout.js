import "../globals.css";
import { AuthProvider } from "../contexts/AuthContext";
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
    "Fikirlerinizi yapay zeka ile sinemaya dönüştürün. Çok-etmenli AI pipeline ile saniyeler içinde sinematik video üretin.",
  keywords: [
    "AI video üretimi",
    "yapay zeka video",
    "sinematik video",
    "MuseForge",
    "agentic AI",
    "video studio",
  ],
  authors: [{ name: "MuseForge", url: BASE_URL }],
  creator: "MuseForge",
  openGraph: {
    type: "website",
    locale: "tr_TR",
    alternateLocale: "en_US",
    url: BASE_URL,
    siteName: "MuseForge",
    title: "MuseForge — Agentic AI Video Studio",
    description:
      "Fikirlerinizi yapay zeka ile sinemaya dönüştürün. Çok-etmenli AI pipeline ile saniyeler içinde sinematik video üretin.",
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
    description: "Fikirlerinizi yapay zeka ile sinemaya dönüştürün.",
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

export default function RootLayout({ children }) {
  return (
    <html lang="tr">
      <body className="antialiased min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
        <AuthProvider>
          <Navbar />
          {children}
          <CookieConsent />
        </AuthProvider>
      </body>
    </html>
  );
}
