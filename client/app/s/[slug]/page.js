import { notFound } from "next/navigation";
import {
  JsonLd,
  SITE_URL,
  SITE_NAME,
  absoluteUrl,
  organizationSchema,
  breadcrumbSchema,
  videoObjectSchema,
} from "../../../lib/seo";
import {
  getShare,
  resolveShareVideo,
  shareUrl,
  embedUrl,
  isoDuration,
  SHARE_REVALIDATE,
} from "../../../lib/share";
import SharePage from "../../../components/SharePage";

/**
 * One published film, at one URL, readable by anyone.
 *
 * Rendered on demand and cached for an hour rather than statically generated:
 * shares are minted by users after the build, so there is no set of slugs to
 * pre-render, and an hour is the longest a revoked page may stay up.
 */
export const revalidate = SHARE_REVALIDATE;
export const dynamicParams = true;

export async function generateMetadata({ params: { slug } }) {
  const share = await getShare(slug);
  if (!share) {
    // A revoked or unknown share. Say noindex explicitly: Next renders the
    // metadata before notFound() takes over, and a 404 body that inherits an
    // indexable default is how dead share URLs would accumulate in the index.
    return { title: `${SITE_NAME}`, robots: { index: false, follow: false } };
  }

  const title = share.title;
  const description =
    share.logline ||
    `A ${share.scene_count}-scene cinematic short generated with ${SITE_NAME}.`;
  const url = shareUrl(slug);
  const video = resolveShareVideo(share);

  return {
    title: { absolute: `${title} | ${SITE_NAME}` },
    description,
    /* No hreflang cluster: this page has exactly one language version, so a
       self-canonical is the whole truth about it. */
    alternates: { canonical: url },
    openGraph: {
      type: "video.other",
      siteName: SITE_NAME,
      title,
      description,
      url,
      ...(share.poster_url ? { images: [{ url: share.poster_url }] } : {}),
      videos: video
        ? [{ url: video, type: "video/mp4", ...aspectDimensions(share.aspect_ratio) }]
        : [],
    },
    twitter: {
      /* `player` rather than `summary_large_image`: it is the card that plays
         the film inside the tweet instead of linking away from it, which is
         the entire point of publishing the page. */
      card: "player",
      title,
      description,
      site: "@museforge_ai",
      ...(share.poster_url ? { images: [share.poster_url] } : {}),
      players: [
        {
          playerUrl: embedUrl(slug),
          streamUrl: video || undefined,
          ...aspectDimensions(share.aspect_ratio),
        },
      ],
    },
    robots: {
      index: true,
      follow: true,
      googleBot: { index: true, follow: true, "max-image-preview": "large" },
    },
  };
}

/** Card and og:video dimensions for an aspect ratio. Twitter requires both. */
function aspectDimensions(aspect) {
  if (aspect === "9:16") return { width: 405, height: 720 };
  if (aspect === "1:1") return { width: 600, height: 600 };
  return { width: 720, height: 405 };
}

export default async function SharedFilmPage({ params: { slug } }) {
  const share = await getShare(slug);
  if (!share) notFound();

  const video = resolveShareVideo(share);
  const graph = [
    organizationSchema(),
    videoObjectSchema({
      slug,
      name: share.title,
      description: share.logline || share.title,
      thumbnailUrl: share.poster_url || undefined,
      contentUrl: video || undefined,
      embedUrl: embedUrl(slug),
      uploadDate: share.shared_at || share.created_at || undefined,
      duration: isoDuration(share.duration_seconds),
      inLanguage: share.language || undefined,
    }),
    breadcrumbSchema([
      { name: SITE_NAME, path: "/" },
      { name: share.title, path: `/s/${slug}` },
    ]),
  ];

  return (
    <>
      <JsonLd graph={graph} />
      <SharePage share={share} videoUrl={video} pageUrl={absoluteUrl(`/s/${slug}`)} />
    </>
  );
}
