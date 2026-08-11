import PricingContent from "./PricingContent";
import { t } from "../../../lib/i18n/index";
import { isLocale, DEFAULT_LOCALE } from "../../../lib/i18n/routing";
import { JsonLd, SITE_URL, absoluteUrl, canonical, faqSchema, openGraphFor } from "../../../lib/seo";

const PATH = "/pricing";

/* Mirrors the plan table in PricingContent. Kept in sync manually — the
   component builds its plans from client-side translations. */
/* The page leads with annual, so the structured data does too: `price` is the
   annual monthly-equivalent (10% off) that a rich result would show, and the
   monthly rate rides along as a second Offer rather than being the headline. */
const PLAN_OFFERS = [
  { name: "Free", price: "0", desc: "Demo mode with placeholder assets — no API key required.", period: null },
  { name: "Creator (annual)", price: "53", desc: "16 credits per month for creators and educators, billed yearly.", period: "P1Y" },
  { name: "Creator (monthly)", price: "59", desc: "16 credits per month for creators and educators.", period: "P1M" },
  { name: "Pro (annual)", price: "116", desc: "36 credits per month for agencies and corporate teams, billed yearly.", period: "P1Y" },
  { name: "Pro (monthly)", price: "129", desc: "36 credits per month for agencies and corporate teams.", period: "P1M" },
];

const FAQ_KEYS = [1, 2, 3, 4];

const EN_TITLE = "Pricing — Plans & Credits";
const EN_DESCRIPTION =
  "MuseForge pricing: start free with demo mode, then scale to Creator (from $53/mo) or Pro (from $116/mo) — 10% off when billed yearly. One credit is 8 seconds of finished film. Buy extra credits any time, cancel whenever you like.";

export function generateMetadata({ params: { locale } }) {
  if (!isLocale(locale)) return {};
  /* English keeps the keyword-tuned copy. Other locales use the translated
     page strings — weaker as a snippet, but it matches what the URL serves. */
  const title = locale === DEFAULT_LOCALE ? EN_TITLE : t(locale, "nav_pricing");
  const description =
    locale === DEFAULT_LOCALE ? EN_DESCRIPTION : t(locale, "pricing_sub");
  return {
    title,
    description,
    alternates: canonical(PATH, locale),
    openGraph: openGraphFor({ title, description, path: PATH, locale }),
  };
}

export default function PricingPage({ params: { locale } }) {
  const faq = FAQ_KEYS.map((n) => ({
    q: t(locale, `pricing_faq_${n}_q`),
    a: t(locale, `pricing_faq_${n}_a`),
  }));

  const product = {
    "@type": "Product",
    "@id": `${SITE_URL}/pricing#product`,
    name: "MuseForge",
    description:
      "Agentic AI video studio that turns a text idea into a cinematic micro-drama.",
    brand: { "@id": `${SITE_URL}/#organization` },
    offers: PLAN_OFFERS.map((p) => ({
      "@type": "Offer",
      name: `${p.name} plan`,
      description: p.desc,
      price: p.price,
      priceCurrency: "USD",
      url: absoluteUrl("/pricing"),
      availability: "https://schema.org/InStock",
      ...(p.period
        ? {
            priceSpecification: {
              "@type": "UnitPriceSpecification",
              price: p.price,
              priceCurrency: "USD",
              billingDuration: p.period === "P1Y" ? 12 : 1,
              billingIncrement: 1,
              unitCode: "MON",
            },
          }
        : {}),
    })),
  };

  /* No BreadcrumbList here: /pricing is top level, so there is no visible
     trail to back the markup up. Breadcrumbs live on /solutions/*. */
  return (
    <>
      <JsonLd graph={[product, faqSchema(faq)]} />
      <PricingContent />
    </>
  );
}
