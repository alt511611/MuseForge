import "../../globals.css";
import { AuthProvider } from "../../contexts/AuthContext";
import { LanguageProvider } from "../../contexts/LanguageContext";
import { DEFAULT_LOCALE } from "../../lib/i18n/routing";
import { getDictionary } from "../../lib/i18n/dictionary";

/**
 * Second root layout. /auth/* stays outside app/[locale] because its URLs are
 * registered as Supabase redirect targets and must not move or gain a prefix.
 * It is noindex, so serving it in the default language only is fine.
 */
export const metadata = {
  title: "MuseForge",
  robots: { index: false, follow: false },
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#07070b",
  colorScheme: "dark",
};

export default function AuthLayout({ children }) {
  return (
    <html lang={DEFAULT_LOCALE} dir="ltr">
      <body className="antialiased min-h-screen" style={{ backgroundColor: "var(--mf-stage)" }}>
        <AuthProvider>
          <LanguageProvider
            locale={DEFAULT_LOCALE}
            dictionary={getDictionary(DEFAULT_LOCALE)}
          >
            {children}
          </LanguageProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
