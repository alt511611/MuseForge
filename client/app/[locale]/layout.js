import "../../globals.css";
import { notFound } from "next/navigation";
import { AuthProvider } from "../../contexts/AuthContext";
import { LanguageProvider } from "../../contexts/LanguageContext";
import Navbar from "../../components/Navbar";
import CookieConsent from "../../components/CookieConsent";
import { SITE_URL, canonical } from "../../lib/seo";
import { t } from "../../lib/i18n/index";
import { getDictionary } from "../../lib/i18n/dictionary";
import {
  LOCALE_CODES,
  isLocale,
  textDirection,
  ogLocale,
} from "../../lib/i18n/routing";

const BASE_URL = SITE_URL;

/* Prerender all 20 locales. English is served unprefixed via the middleware
   rewrite, so /pricing and /tr/pricing are both static. */
export function generateStaticParams() {
  return LOCALE_CODES.map((locale) => ({ locale }));
}

export function generateMetadata({ params: { locale } }) {
  if (!isLocale(locale)) return {};

  const title = `MuseForge — ${t(locale, "hero_sub")}`;
  const description = t(locale, "hero_desc");

  return {
    metadataBase: new URL(BASE_URL),
    title: { default: title, template: "%s | MuseForge" },
    description,
    alternates: canonical("/", locale),
    applicationName: "MuseForge",
    category: "technology",
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
    // Set NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION / _BING_ to the token from the
    // console; omitting the env var simply omits the meta tag.
    verification: {
      google: process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION || undefined,
      other: process.env.NEXT_PUBLIC_BING_SITE_VERIFICATION
        ? { "msvalidate.01": process.env.NEXT_PUBLIC_BING_SITE_VERIFICATION }
        : undefined,
    },
    openGraph: {
      type: "website",
      locale: ogLocale(locale),
      alternateLocale: LOCALE_CODES.filter((c) => c !== locale).map(ogLocale),
      siteName: "MuseForge",
      title,
      description,
      // Social card comes from app/opengraph-image.js (file convention).
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
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
      icon: [
        { url: "/favicon.ico", sizes: "any" },
        { url: "/icon-192.png", type: "image/png", sizes: "192x192" },
        { url: "/icon-512.png", type: "image/png", sizes: "512x512" },
      ],
      shortcut: "/favicon.ico",
      apple: "/apple-touch-icon.png",
    },
  };
}

export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: "#07070b",
  colorScheme: "dark",
};

export default function RootLayout({ children, params: { locale } }) {
  // A bare /xx/ path that isn't a supported locale must 404 rather than render
  // the English site under a bogus prefix (that would create duplicate URLs).
  if (!isLocale(locale)) notFound();

  return (
    <html lang={locale} dir={textDirection(locale)}>
      <body className="antialiased min-h-screen" style={{ backgroundColor: "var(--mf-stage)" }}>
        <AuthProvider>
          {/* One language, assembled here on the server. Importing the
              dictionaries inside the provider (a client component) is what
              used to ship all twenty to every reader. */}
          <LanguageProvider locale={locale} dictionary={getDictionary(locale)}>
            <Navbar />
            {children}
            <CookieConsent />
          </LanguageProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
