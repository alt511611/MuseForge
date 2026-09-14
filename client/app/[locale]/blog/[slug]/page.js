import { notFound } from "next/navigation";
import ArticleLayout from "../../../../components/ArticleLayout";
import Breadcrumbs from "../../../../components/Breadcrumbs";
import {
  JsonLd,
  canonical,
  openGraphFor,
  breadcrumbSchema,
  blogSchema,
  articleSchema,
  howToSchema,
  faqSchema,
} from "../../../../lib/seo";
import { t } from "../../../../lib/i18n/index";
import { isLocale, withLocale } from "../../../../lib/i18n/routing";
import {
  BLOG_PATH,
  loadArticle,
  articleCard,
  articlePath,
  findArticle,
  articlesIn,
} from "../../../../lib/content";
import { articleLabels } from "../../../../lib/content/labels";
import { faqItems, howToBlocks, readingMinutes } from "../../../../lib/content/blocks";

/**
 * Only the (locale, slug) pairs that have a body. An article written in English
 * and Turkish is two pages, not twenty — see the translation policy in
 * lib/content/index.js. `dynamicParams` is off so anything else is a 404 rather
 * than an on-demand render of a page that cannot exist.
 */
export const dynamicParams = false;

export function generateStaticParams({ params: { locale } }) {
  return articlesIn(locale).map((a) => ({ slug: a.slug }));
}

export function generateMetadata({ params: { locale, slug } }) {
  if (!isLocale(locale)) return {};
  const article = loadArticle(slug, locale);
  if (!article) return {};

  const path = articlePath(slug);
  return {
    title: { absolute: `${article.title} | MuseForge` },
    description: article.description,
    alternates: canonical(path, locale, article.locales),
    openGraph: openGraphFor({
      title: article.title,
      description: article.description,
      path,
      locale,
      type: "article",
      available: article.locales,
      article: {
        publishedTime: article.published,
        modifiedTime: article.updated || article.published,
        authors: ["MuseForge"],
        tags: article.tags,
      },
    }),
  };
}

export default function ArticlePage({ params: { locale, slug } }) {
  const article = loadArticle(slug, locale);
  if (!article) notFound();

  const path = articlePath(slug);
  const labels = articleLabels(locale);

  const TRAIL = [
    { name: t(locale, "nav_home"), path: withLocale("/", locale) },
    { name: t(locale, "blog_title"), path: withLocale(BLOG_PATH, locale) },
    { name: article.title, path: withLocale(path, locale) },
  ];

  /* Related posts are named by the article and filtered to this locale, so a
     Turkish reader is never handed a card that leads to a 404. Anything left
     over is filled from the rest of the catalogue in this language. */
  const named = (article.related || [])
    .map(findArticle)
    .filter((a) => a && a.locales?.[locale]);
  const fill = articlesIn(locale).filter(
    (a) => a.slug !== slug && !named.some((n) => n.slug === a.slug)
  );
  const related = [...named, ...fill].slice(0, 2).map((a) => articleCard(a, locale));

  /* The structured data is derived from the same blocks the reader sees --
     every FAQPage question and every HowTo step is text that is visibly on the
     page, which is the condition Google attaches to both rich results. */
  const faq = faqItems(article.blocks);
  const howTos = howToBlocks(article.blocks).map((h) =>
    howToSchema({ path, locale, ...h })
  );

  return (
    <>
      <JsonLd
        graph={[
          blogSchema(locale),
          breadcrumbSchema(TRAIL),
          articleSchema({
            path,
            locale,
            headline: article.headline,
            description: article.description,
            published: article.published,
            updated: article.updated,
            section: labels.categories?.[article.category] || article.category,
            keywords: article.tags,
            wordCount: readingMinutes(article.blocks) * 220,
            summary: article.summary,
          }),
          ...howTos,
          ...(faq.length ? [faqSchema(faq)] : []),
        ]}
      />
      <ArticleLayout
        article={article}
        related={related}
        labels={labels}
        breadcrumbs={<Breadcrumbs trail={TRAIL} />}
      />
    </>
  );
}
