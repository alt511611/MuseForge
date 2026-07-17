"use client";

import Link from "next/link";
import { useLanguage } from "../../../contexts/LanguageContext";

const Section = ({ title, children }) => (
  <section className="mb-8">
    <h2 className="text-lg font-semibold mb-3" style={{ color: "#a78bfa" }}>{title}</h2>
    <div className="text-sm leading-relaxed space-y-2" style={{ color: "#94a3b8" }}>{children}</div>
  </section>
);

export default function TermsContent() {
  const { t, locale } = useLanguage();
  const updated = new Date().toLocaleDateString(locale === "en" ? "en-US" : locale, {
    year: "numeric", month: "long", day: "numeric",
  });

  return (
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      <div className="max-w-3xl mx-auto px-6 py-16">
        <Link href="/" className="text-sm mb-8 inline-block hover:text-purple-400 transition-colors" style={{ color: "#64748b" }}>
          {t("terms_home")}
        </Link>

        <h1 className="text-3xl font-black gradient-text mb-2">{t("terms_title")}</h1>
        <p className="text-xs mb-10" style={{ color: "#475569" }}>{t("terms_updated")}: {updated}</p>

        <div className="glass rounded-2xl p-8">
          <Section title="1. Description of Service">
            <p>
              MuseForge is an AI-powered video generation platform. By accessing the service,
              you agree to these terms.
            </p>
          </Section>

          <Section title="2. Account Creation and Security">
            <ul className="list-disc list-inside space-y-1">
              <li>You must be at least 18 years old to create an account.</li>
              <li>You are responsible for maintaining the confidentiality of your account credentials.</li>
              <li>You are responsible for all actions taken from your account.</li>
              <li>Contact us immediately if you notice any suspicious activity.</li>
            </ul>
          </Section>

          <Section title="3. Acceptable Use">
            <p>You agree not to use MuseForge to create illegal, harmful, hateful, or sexually explicit content involving minors, or to infringe others&apos; intellectual property.</p>
          </Section>

          <Section title="4. Credits and Billing">
            <ul className="list-disc list-inside space-y-1">
              <li>Paid plans and credit packages are billed via Stripe.</li>
              <li>Free plan credits reset monthly based on plan terms.</li>
              <li>Unused subscription credits do not roll over unless stated otherwise.</li>
            </ul>
          </Section>

          <Section title="5. Intellectual Property">
            <p>Subject to these terms, you own the videos you generate. MuseForge retains rights to the platform, models, and underlying software.</p>
          </Section>

          <Section title="6. Limitation of Liability">
            <p>The service is provided &quot;as is&quot;. MuseForge is not liable for indirect or consequential damages arising from use of the platform.</p>
          </Section>

          <Section title="7. Termination">
            <p>We may suspend or terminate accounts that violate these terms. You may close your account at any time.</p>
          </Section>

          <Section title="8. Changes">
            <p>We may update these terms. Continued use after changes constitutes acceptance.</p>
          </Section>

          <Section title="9. Contact">
            <p>Questions about these terms: <a href="mailto:legal@museforge.ai" className="underline" style={{ color: "#a78bfa" }}>legal@museforge.ai</a></p>
          </Section>
        </div>

        <div className="mt-8 flex gap-4 text-xs" style={{ color: "#64748b" }}>
          <Link href="/legal/privacy" className="hover:text-purple-400">{t("privacy_title")}</Link>
          <Link href="/pricing" className="hover:text-purple-400">{t("footer_pricing")}</Link>
        </div>
      </div>
    </main>
  );
}
