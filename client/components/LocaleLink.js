"use client";

import NextLink from "next/link";
import { forwardRef } from "react";
import { useLanguage } from "../contexts/LanguageContext";

/**
 * Drop-in replacement for next/link that keeps the visitor inside their
 * language. A plain <Link href="/pricing"> on /tr/... would drop them back to
 * the English page; this prefixes site-relative hrefs with the active locale.
 *
 * External URLs, mailto:, anchors and the never-localized /auth and /api
 * subtrees pass through untouched (withLocale handles those).
 */
const LocaleLink = forwardRef(function LocaleLink({ href, ...props }, ref) {
  const { localeHref } = useLanguage();
  return <NextLink ref={ref} href={localeHref(href)} {...props} />;
});

export default LocaleLink;
