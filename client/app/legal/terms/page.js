import Link from "next/link";

export const metadata = {
  title: "Terms of Service — MuseForge",
  description: "Please read MuseForge's terms of service before using the platform.",
};

const Section = ({ title, children }) => (
  <section className="mb-8">
    <h2 className="text-lg font-semibold mb-3" style={{ color: "#a78bfa" }}>{title}</h2>
    <div className="text-sm leading-relaxed space-y-2" style={{ color: "#94a3b8" }}>{children}</div>
  </section>
);

export default function TermsPage() {
  return (
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      <div className="max-w-3xl mx-auto px-6 py-16">
        <Link href="/" className="text-sm mb-8 inline-block hover:text-purple-400 transition-colors" style={{ color: "#64748b" }}>
          ← Home
        </Link>

        <h1 className="text-3xl font-black gradient-text mb-2">Terms of Service</h1>
        <p className="text-xs mb-10" style={{ color: "#475569" }}>Last updated: {new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}</p>

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

          <Section title="3. Prohibited Uses">
            <p>The following uses are strictly forbidden:</p>
            <ul className="list-disc list-inside space-y-1">
              <li>Generating illegal, deceptive, or harmful content.</li>
              <li>Creating deepfakes or content intended for identity fraud.</li>
              <li>Infringing copyright or intellectual property rights.</li>
              <li>Unauthorized access to systems or causing service disruptions.</li>
              <li>Generating content inappropriate for minors.</li>
            </ul>
          </Section>

          <Section title="4. Intellectual Property">
            <ul className="list-disc list-inside space-y-1">
              <li><strong style={{ color: "#e2e8f0" }}>Your content:</strong> You retain ownership of the ideas and text inputs you provide to the platform.</li>
              <li><strong style={{ color: "#e2e8f0" }}>Generated content:</strong> Videos produced under your subscription are licensed to you for personal and commercial use. Third-party AI provider terms apply.</li>
              <li><strong style={{ color: "#e2e8f0" }}>Platform:</strong> The MuseForge brand, software, and interface are owned by the company and may not be reproduced.</li>
            </ul>
          </Section>

          <Section title="5. Payment and Subscriptions">
            <ul className="list-disc list-inside space-y-1">
              <li>Paid plans are billed monthly or annually.</li>
              <li>Cancellation takes effect at the next billing date; no prorated refunds are issued.</li>
              <li>Payments are processed securely via Stripe.</li>
              <li>Price changes will be communicated 30 days in advance.</li>
              <li>Free plan credits reset monthly based on plan terms.</li>
            </ul>
          </Section>

          <Section title="6. Limitation of Liability">
            <p>
              To the maximum extent permitted by applicable law, MuseForge is not liable for indirect,
              incidental, or consequential damages. The service is provided &quot;as is&quot; and no
              guarantee of 100% uptime is made.
            </p>
          </Section>

          <Section title="7. Account Termination">
            <ul className="list-disc list-inside space-y-1">
              <li>You may close your account at any time through your account settings.</li>
              <li>Violation of these Terms may result in account suspension or termination.</li>
              <li>Upon closure, data is retained for the period specified in the Privacy Policy.</li>
            </ul>
          </Section>

          <Section title="8. Governing Law and Dispute Resolution">
            <p>
              These Terms are governed by applicable law. Disputes will be resolved through
              binding arbitration or the courts of the jurisdiction in which MuseForge operates.
            </p>
          </Section>

          <Section title="9. Changes">
            <p>
              Terms may be updated. Material changes will be communicated by email.
              Continued use after changes constitutes acceptance of the updated terms.
            </p>
          </Section>

          <Section title="10. Contact">
            <p>
              For questions:{" "}
              <a href="mailto:legal@museforge.ai" className="underline" style={{ color: "#a78bfa" }}>
                legal@museforge.ai
              </a>
            </p>
          </Section>
        </div>

        <div className="mt-6 flex gap-4 text-xs" style={{ color: "#475569" }}>
          <Link href="/legal/privacy" className="underline hover:text-purple-400">Privacy Policy</Link>
          <Link href="/" className="underline hover:text-purple-400">Home</Link>
        </div>
      </div>
    </main>
  );
}
