import BlogIndex from "../../../components/BlogIndex";
import Breadcrumbs from "../../../components/Breadcrumbs";
import {
  JsonLd,
  canonical,
  openGraphFor,
  breadcrumbSchema,
  blogSchema,
  itemListSchema,
} from "../../../lib/seo";
import { t } from "../../../lib/i18n/index";
import { isLocale, withLocale, DEFAULT_LOCALE } from "../../../lib/i18n/routing";
import { ARTICLES, BLOG_PATH, articleCard, articlesIn } from "../../../lib/content";
import { articleLabels } from "../../../lib/content/labels";

const PATH = BLOG_PATH;

/* Locales that actually have at least one article. Only these get an indexable
   index page and a place in the hreflang cluster; the rest still render (a
   visitor on /ja who clicks Guides has to land somewhere) but are marked
   noindex, because their cards would be English copy on a Japanese URL. */
const LOCALES_WITH_ARTICLES = [
  ...new Set(ARTICLES.flatMap((a) => Object.keys(a.locales || {}))),
];

const trail = (locale) => [
  { name: t(locale, "nav_home"), path: withLocale("/", locale) },
  { name: t(locale, "blog_title"), path: withLocale(PATH, locale) },
];

export function generateMetadata({ params: { locale } }) {
  if (!isLocale(locale)) return {};
  const title = `${t(locale, "blog_title")} — ${t(locale, "blog_tagline")}`;
  const description = t(locale, "blog_desc");
  const translated = LOCALES_WITH_ARTICLES.includes(locale);

  return {
    title: { absolute: `${title} | MuseForge` },
    description,
    alternates: canonical(PATH, locale, LOCALES_WITH_ARTICLES),
    openGraph: openGraphFor({
      title,
      description,
      path: PATH,
      locale,
      available: LOCALES_WITH_ARTICLES,
    }),
    ...(translated ? {} : { robots: { index: false, follow: true } }),
  };
}

export default function BlogIndexPage({ params: { locale } }) {
  const own = articlesIn(locale);
  const translated = own.length > 0;
  /* Falling back to the English set rather than showing an empty page: the
     articles exist, they are just not in this language yet, and a dead end is
     worse than a card that says so. */
  const source = translated ? own : articlesIn(DEFAULT_LOCALE);
  const cards = source.map((a) => articleCard(a, locale));
  const TRAIL = trail(locale);

  return (
    <>
      <JsonLd
        graph={[
          blogSchema(locale),
          breadcrumbSchema(TRAIL),
          itemListSchema({ path: PATH, locale, items: cards }),
        ]}
      />
      <BlogIndex
        locale={locale}
        breadcrumbs={<Breadcrumbs trail={TRAIL} />}
        heading={t(locale, "blog_title")}
        tagline={t(locale, "blog_tagline")}
        intro={t(locale, "blog_desc")}
        notice={translated ? null : t(locale, "blog_empty")}
        cards={cards}
        labels={articleLabels(locale)}
      />
    </>
  );
}
