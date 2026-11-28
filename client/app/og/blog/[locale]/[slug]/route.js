import { ImageResponse } from "next/og";
import { ARTICLES, loadArticle, localesOf } from "../../../../../lib/content";
import { articleLabels } from "../../../../../lib/content/labels";

/**
 * /og/blog/<locale>/<slug> — one 1200x630 cover per article edition.
 *
 * WHY. Every BlogPosting named /icon-512.png as its image and every article
 * shared the site-wide social card, so all five guides — in every language —
 * presented the same picture to Google, to a share preview and to an answer
 * engine that shows a thumbnail beside its citation. Google's Article guidance
 * asks for an image at least 1200 px wide that represents the article; a
 * square logo is neither. Five identical cards in a feed also read as one
 * page posted five times.
 *
 * WHY A ROUTE AND NOT opengraph-image.js. The file convention mints a URL
 * under /[locale]/ with a content hash on the end, which is fine for the
 * og:image tag Next writes itself and useless for JSON-LD, which needs a URL
 * it can name in advance. This one is fixed, unlocalized (the middleware
 * leaves /og/ alone) and built once per edition at build time.
 */

export const dynamic = "force-static";
export const dynamicParams = false;

export function generateStaticParams() {
  return ARTICLES.flatMap((a) => localesOf(a).map((locale) => ({ locale, slug: a.slug })));
}

export function GET(_request, { params: { locale, slug } }) {
  const article = loadArticle(slug, locale);
  if (!article) return new Response("Not found", { status: 404 });
  const labels = articleLabels(locale);
  const section = labels.categories?.[article.category] || article.category;

  /* Satori does not shrink text to fit. The longest English title is 64
     characters; below 50 it can afford the larger size without a third line. */
  const fontSize = article.title.length > 50 ? 62 : 72;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "72px 80px",
          backgroundColor: "#07070b",
          backgroundImage:
            "radial-gradient(ellipse 70% 60% at 50% 0%, #6d28d955 0%, transparent 70%)",
          color: "#f1f3f8",
          fontFamily: "sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "18px",
            fontSize: 26,
            letterSpacing: "0.3em",
            textTransform: "uppercase",
            color: "#b9a5fb",
          }}
        >
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: 11,
              background: "linear-gradient(135deg,#8b5cf6,#6d28d9)",
            }}
          />
          {`MuseForge · ${section}`}
        </div>

        <div
          style={{
            display: "flex",
            fontSize,
            fontWeight: 700,
            lineHeight: 1.12,
            letterSpacing: "-0.02em",
          }}
        >
          {article.title}
        </div>

        <div style={{ display: "flex", fontSize: 28, color: "#a8b0c2" }}>
          museforge.studio/blog
        </div>
      </div>
    ),
    { width: 1200, height: 630 }
  );
}
