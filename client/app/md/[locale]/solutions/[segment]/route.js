import { SEGMENT_KEYS } from "../../../../../lib/content/pages";
import { mdResponse, mdStaticParams } from "../../../../../lib/content/mdRoute";

/**
 * /md/<locale>/solutions/<segment> — one segment page as Markdown.
 *
 * Only the English edition is generated, because only English exists: the four
 * segment pages are untranslated (see any of their content.js). Prerendering
 * twenty identical English copies under twenty locale prefixes would be twenty
 * URLs serving one document, which is the duplicate-content problem the share
 * routes were kept out of the locale tree to avoid.
 */
export const dynamic = "force-static";
export const dynamicParams = false;

export function generateStaticParams() {
  return SEGMENT_KEYS.flatMap((segment) =>
    mdStaticParams(segment).map((p) => ({ ...p, segment }))
  );
}

export function GET(_request, { params: { locale, segment } }) {
  return mdResponse(segment, locale);
}
