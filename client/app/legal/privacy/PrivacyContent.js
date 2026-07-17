"use client";

import Link from "next/link";
import { useLanguage } from "../../../contexts/LanguageContext";

const Section = ({ title, children }) => (
  <section className="mb-8">
    <h2 className="text-lg font-semibold mb-3" style={{ color: "#a78bfa" }}>{title}</h2>
    <div className="text-sm leading-relaxed space-y-2" style={{ color: "#94a3b8" }}>{children}</div>
  </section>
);

export default function PrivacyContent() {
  const { t, locale } = useLanguage();
  const updated = new Date().toLocaleDateString(locale === "en" ? "en-US" : locale, {
    year: "numeric", month: "long", day: "numeric",
  });

  return (
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      <div className="max-w-3xl mx-auto px-6 py-16">
        <Link href="/" className="text-sm mb-8 inline-block hover:text-purple-400 transition-colors" style={{ color: "#64748b" }}>
          {t("privacy_home")}
        </Link>

        <h1 className="text-3xl font-black gradient-text mb-2">{t("privacy_title")}</h1>
        <p className="text-xs mb-10" style={{ color: "#475569" }}>{t("privacy_updated")}: {updated}</p>

        <div className="glass rounded-2xl p-8">
          <Section title="1. Data We Collect">
            <p>Account email, authentication identifiers, generation job metadata, billing records via Stripe, and basic usage analytics.</p>
          </Section>

          <Section title="2. How We Use Data">
            <p>To provide and improve the service, process payments, prevent abuse, and communicate account-related notices.</p>
          </Section>

          <Section title="3. Sharing">
            <p>We share data with processors such as Supabase (auth/database/storage), Stripe (payments), and hosting providers as needed to run MuseForge. We do not sell personal data.</p>
          </Section>

          <Section title="4. Retention">
            <p>We retain account and job data while your account is active and as required for legal or billing obligations.</p>
          </Section>

          <Section title="5. Your Rights">
            <p>Depending on your region, you may request access, correction, or deletion of your personal data by contacting us.</p>
          </Section>

          <Section title="6. Cookies">
            <p>We use essential cookies for authentication and preferences (including language). See the on-site cookie banner for choices.</p>
          </Section>

          <Section title="7. Contact">
            <p>Privacy questions: <a href="mailto:privacy@museforge.ai" className="underline" style={{ color: "#a78bfa" }}>privacy@museforge.ai</a></p>
          </Section>
        </div>

        <div className="mt-8 flex gap-4 text-xs" style={{ color: "#64748b" }}>
          <Link href="/legal/terms" className="hover:text-purple-400">{t("terms_title")}</Link>
          <Link href="/pricing" className="hover:text-purple-400">{t("footer_pricing")}</Link>
        </div>
      </div>
    </main>
  );
}
