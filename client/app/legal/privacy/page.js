import Link from "next/link";

export const metadata = {
  title: "Privacy Policy — MuseForge",
  description: "How MuseForge collects, uses, and protects your personal data.",
};

const Section = ({ title, children }) => (
  <section className="mb-8">
    <h2 className="text-lg font-semibold mb-3" style={{ color: "#a78bfa" }}>{title}</h2>
    <div className="text-sm leading-relaxed space-y-2" style={{ color: "#94a3b8" }}>{children}</div>
  </section>
);

export default function PrivacyPage() {
  return (
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      <div className="max-w-3xl mx-auto px-6 py-16">
        <Link href="/" className="text-sm mb-8 inline-block hover:text-purple-400 transition-colors" style={{ color: "#64748b" }}>
          ← Home
        </Link>

        <h1 className="text-3xl font-black gradient-text mb-2">Privacy Policy</h1>
        <p className="text-xs mb-10" style={{ color: "#475569" }}>Last updated: {new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}</p>

        <div className="glass rounded-2xl p-8">
          <Section title="1. Data Controller">
            <p>
              MuseForge ("Company", "we") acts as the data controller under applicable data protection laws,
              including the GDPR. This policy explains what personal data we collect, how we use it, and your rights.
            </p>
          </Section>

          <Section title="2. Personal Data We Collect">
            <ul className="list-disc list-inside space-y-1">
              <li><strong style={{ color: "#e2e8f0" }}>Identity / Contact:</strong> Email address provided during registration.</li>
              <li><strong style={{ color: "#e2e8f0" }}>Usage Data:</strong> Video generation requests, preferences, and session information.</li>
              <li><strong style={{ color: "#e2e8f0" }}>Payment Information:</strong> Payments are processed by Stripe; card details are never stored on MuseForge servers.</li>
              <li><strong style={{ color: "#e2e8f0" }}>Technical Data:</strong> IP address, browser type, and page interactions (for analytics).</li>
              <li><strong style={{ color: "#e2e8f0" }}>Cookies:</strong> Used for session management and preference storage.</li>
            </ul>
          </Section>

          <Section title="3. Purposes and Legal Bases">
            <ul className="list-disc list-inside space-y-1">
              <li>Providing the service and account management (contract performance).</li>
              <li>Payment and subscription management (contract performance / legal obligation).</li>
              <li>Service security and fraud prevention (legitimate interest).</li>
              <li>Diagnosing and resolving technical issues (legitimate interest).</li>
              <li>Marketing communications (with explicit consent only).</li>
            </ul>
          </Section>

          <Section title="4. Data Sharing">
            <p>
              Your personal data is not shared with third parties except service providers (Supabase, Stripe,
              Vercel, Render), legal obligations, or with your explicit consent. International transfers are
              made with appropriate safeguards under applicable law.
            </p>
          </Section>

          <Section title="5. Retention Periods">
            <ul className="list-disc list-inside space-y-1">
              <li>Account data: until account closure, then 6 months.</li>
              <li>Payment records: 10 years as required by law.</li>
              <li>Technical logs: 90 days.</li>
            </ul>
          </Section>

          <Section title="6. Your Rights (GDPR / Data Protection)">
            <p>You have the right to:</p>
            <ul className="list-disc list-inside space-y-1">
              <li>Know whether your personal data is being processed.</li>
              <li>Request information about processed data.</li>
              <li>Understand the purpose and whether it is used accordingly.</li>
              <li>Know the third parties to whom data is transferred.</li>
              <li>Request correction of incomplete or inaccurate data.</li>
              <li>Request erasure or destruction of your data.</li>
              <li>Object to decisions made solely by automated systems.</li>
              <li>Claim compensation for any resulting damages.</li>
            </ul>
            <p className="mt-2">
              To make a request:{" "}
              <a href="mailto:privacy@museforge.ai" className="underline" style={{ color: "#a78bfa" }}>
                privacy@museforge.ai
              </a>
            </p>
          </Section>

          <Section title="7. Cookies">
            <p>
              Essential cookies are used for session management. You can manage your analytics cookie
              preferences through the cookie banner at the bottom of the page.
            </p>
          </Section>

          <Section title="8. Changes">
            <p>
              This policy may be updated. Material changes will be communicated via email.
              The current version is always published on this page.
            </p>
          </Section>
        </div>

        <div className="mt-6 flex gap-4 text-xs" style={{ color: "#475569" }}>
          <Link href="/legal/terms" className="underline hover:text-purple-400">Terms of Service</Link>
          <Link href="/" className="underline hover:text-purple-400">Home</Link>
        </div>
      </div>
    </main>
  );
}
