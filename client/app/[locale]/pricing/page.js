import PricingContent from "./PricingContent";
import { t } from "../../../lib/i18n/index";
import { isLocale, DEFAULT_LOCALE } from "../../../lib/i18n/routing";
import { PLAN_OFFERS } from "../../../lib/pricing";
import {
  JsonLd,
  SITE_URL,
  absoluteUrl,
  canonical,
  faqSchema,
  openGraphFor,
  organizationSchema,
} from "../../../lib/seo";

const PATH = "/pricing";

const FAQ_KEYS = [1, 2, 3, 4];

const EN_TITLE = "Pricing — Plans & Credits";
const EN_DESCRIPTION =
  "MuseForge pricing: start free with demo mode, then scale to Creator (from $53/mo) or Pro (from $116/mo) — 10% off when billed yearly. One credit is 10 seconds of finished film. Buy extra credits any time, cancel whenever you like.";

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
    /* Required, not optional: Search Console rejects a Product without an
       image as a critical error and drops the whole node, taking the price
       offers with it. The social card is the only 1200x630 image the site
       generates, and it is generated at build time, so it costs nothing. */
    image: [absoluteUrl("/opengraph-image")],
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
      {/* organizationSchema travels with the product rather than being assumed:
          structured data is read one page at a time, so `brand` pointing at
          /#organization resolved to nothing here and Search Console reported
          the brand as having no name. A cross-page @id is not a reference, it
          is a dangling pointer. */}
      <JsonLd graph={[organizationSchema(), product, faqSchema(faq)]} />
      <PricingContent />
    </>
  );
}
