import { notFound } from "next/navigation";
import { getShare, resolveShareVideo, shareUrl, SHARE_REVALIDATE } from "../../../lib/share";
import EmbedPlayer from "../../../components/EmbedPlayer";

/**
 * The film, and nothing else, for an <iframe> on somebody else's site.
 *
 * The canonical points back at /s/{slug} — belt and braces alongside the
 * noindex header, because a URL that gets linked from a hundred blog posts
 * should pass that signal to the page it is a stripped-down copy of.
 */
export const revalidate = SHARE_REVALIDATE;
export const dynamicParams = true;

export async function generateMetadata({ params: { slug } }) {
  const share = await getShare(slug);
  return {
    title: share ? `${share.title} | MuseForge` : "MuseForge",
    alternates: { canonical: shareUrl(slug) },
    robots: { index: false, follow: true },
  };
}

export default async function EmbedPage({ params: { slug } }) {
  const share = await getShare(slug);
  if (!share) notFound();

  return (
    <EmbedPlayer
      src={resolveShareVideo(share)}
      poster={share.poster_url}
      title={share.title}
      href={shareUrl(slug)}
    />
  );
}
