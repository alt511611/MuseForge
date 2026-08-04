import LoginContent from "./LoginContent";
import { canonical } from "../../../lib/seo";
import { isLocale } from "../../../lib/i18n/routing";

export function generateMetadata({ params: { locale } }) {
  if (!isLocale(locale)) return {};
  return {
    title: "Sign In",
    description:
      "Sign in to MuseForge to generate cinematic AI videos, manage your credits, and download your finished micro-dramas.",
    alternates: canonical("/login", locale),
    robots: { index: false, follow: true },
  };
}

export default function LoginPage() {
  return <LoginContent />;
}
