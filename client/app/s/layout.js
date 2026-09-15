import "../../globals.css";
import { AuthProvider } from "../../contexts/AuthContext";
import { LanguageProvider } from "../../contexts/LanguageContext";
import Navbar from "../../components/Navbar";
import CookieConsent from "../../components/CookieConsent";
import { SITE_URL } from "../../lib/seo";
import { DEFAULT_LOCALE } from "../../lib/i18n/routing";
import { getDictionary } from "../../lib/i18n/dictionary";

/**
 * Third root layout. /s/* stays outside app/[locale] because a share is ONE
 * page per film rather than twenty (see UNLOCALIZED_PREFIXES in
 * lib/i18n/routing.js): the only text a reader comes for is the film's own
 * title and logline, in the language it was written in, so localizing the
 * chrome around it would mint nineteen near-duplicate URLs per share.
 *
 * `metadataBase` is restated here because a root layout does not inherit it
 * from a sibling — without it every og:image on a share page resolves relative
 * to nothing and Twitter drops the card.
 */
export const metadata = {
  metadataBase: new URL(SITE_URL),
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: "#07070b",
  colorScheme: "dark",
};

export default function ShareLayout({ children }) {
  return (
    <html lang={DEFAULT_LOCALE} dir="ltr">
      <body className="antialiased min-h-screen" style={{ backgroundColor: "var(--mf-stage)" }}>
        <AuthProvider>
          <LanguageProvider
            locale={DEFAULT_LOCALE}
            dictionary={getDictionary(DEFAULT_LOCALE)}
          >
            <Navbar />
            {children}
            <CookieConsent />
          </LanguageProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
