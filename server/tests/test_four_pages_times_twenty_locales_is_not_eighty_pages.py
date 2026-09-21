"""Four segment pages, each rendered at twenty locale prefixes, each declaring
itself the original.

Search Console found this before this test did. On museforge.studio,
/th/solutions/education came back "Duplicate without user-selected canonical" --
Google had noticed the page's body is byte-identical to /solutions/education
(the four /solutions/* pages' copy lives in one English-only content.js; see
that file's own docstring) and started consolidating on its own, because the
site never told it which of the twenty near-identical URLs was the real one.
Of the "Discovered - currently not indexed: 101" figure in the same report,
most of the mass is these four pages' nineteen extra locale prefixes each --
76 URLs of duplicate content sitting in a low-priority crawl queue instead of
the blog articles that are actually worth a crawl budget.

lib/seo.js's canonical() used to compute `canonical: withLocale(path, locale)`
unconditionally -- every locale self-referencing, regardless of whether that
locale's content is its own or borrowed. The fix adds a locale that is NOT in
the page's declared `available` set falls back to that set's first entry
(English, for these four pages) instead of pointing at itself. openGraphFor
gets the same treatment for the same reason: og:url is a dedup signal too.

This test does not execute the JS -- there is no JS test runner in this repo,
and lib/seo.js ends in a JSX-returning component that a plain Node script
cannot import without a transpiler. It checks the same thing every other
client-side test in this suite checks: that the specific mistake cannot be
reintroduced without the assertion noticing, by scanning the source for the
call shape rather than the string.
"""

import os
import re

import pytest

CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "client")
SEO = os.path.join(CLIENT, "lib", "seo.js")
SITEMAP = os.path.join(CLIENT, "app", "sitemap.js")
SOLUTIONS = os.path.join(CLIENT, "app", "[locale]", "solutions")

#: The segments that each have a page under app/[locale]/solutions, and whose
#: content.js is English only (see that file's own docstring on each).
SEGMENTS = ("agencies", "creators", "education", "filmmakers")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _strip_comments(source):
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*", " ", source)


def test_canonical_stops_self_referencing_for_a_locale_outside_available():
    """The unconditional self-reference this bug came from must be gone, and
    the replacement must actually consult the `available` set it is handed --
    not just exist as an unused local."""
    source = _strip_comments(_read(SEO))

    assert "canonical: withLocale(path, locale)," not in source, (
        "canonical() reverted to always self-referencing -- this is exactly "
        "the bug Search Console found on /th/solutions/education"
    )

    canonical_fn = re.search(
        r"export function canonical\([^)]*\)\s*\{.*?\n\}", source, re.S
    )
    assert canonical_fn, "canonical() not found in lib/seo.js"
    body = canonical_fn.group(0)

    assert "codes.includes(locale)" in body, (
        "canonical() must branch on whether the requested locale is in the "
        "page's own available set before deciding what to self-reference"
    )
    assert "canonical: withLocale(path, canonicalLocale)," in body, (
        "canonical() must emit the computed fallback locale, not the raw "
        "locale parameter, in the canonical field"
    )


def test_open_graph_url_gets_the_same_fallback_as_canonical():
    """og:url is Facebook's and LinkedIn's dedup key. A page that fixed its
    <link rel=canonical> but left og:url self-referencing still tells half of
    the internet that twenty copies are twenty originals."""
    source = _strip_comments(_read(SEO))
    og_fn = re.search(
        r"export function openGraphFor\(\{.*?\n\}\n\n", source, re.S
    )
    assert og_fn, "openGraphFor() not found in lib/seo.js"
    body = og_fn.group(0)

    assert "url: withLocale(path, canonicalLocale)," in body, (
        "openGraphFor() must point og:url at the same fallback locale as "
        "canonical(), not at the raw `locale` parameter"
    )


@pytest.mark.parametrize("segment", SEGMENTS)
def test_solution_page_declares_english_as_its_only_locale(segment):
    """Each segment page's content is English only (content.js says so in its
    own docstring). Its metadata must say so too, or the twenty locale
    prefixes this route still renders for keep self-canonicalizing."""
    path = os.path.join(SOLUTIONS, segment, "page.js")
    source = _strip_comments(_read(path))

    assert re.search(r"const ONLY_LOCALE\s*=\s*\[\s*DEFAULT_LOCALE\s*\]", source), (
        f"{segment}/page.js must declare ONLY_LOCALE = [DEFAULT_LOCALE]"
    )

    canonical_call = re.search(r"canonical\(([^)]*)\)", source)
    assert canonical_call, f"{segment}/page.js does not call canonical()"
    args = [a.strip() for a in canonical_call.group(1).split(",")]
    assert len(args) == 3 and args[2] == "ONLY_LOCALE", (
        f"{segment}/page.js must call canonical(PATH, locale, ONLY_LOCALE) -- "
        f"got canonical({canonical_call.group(1)}), which self-canonicalizes "
        "every one of its twenty locale prefixes"
    )

    assert re.search(r"openGraphFor\(\{[^}]*available:\s*ONLY_LOCALE", source, re.S), (
        f"{segment}/page.js's openGraphFor() call must pass available: ONLY_LOCALE"
    )


def test_sitemap_lists_one_url_per_solution_page_not_twenty():
    """A sitemap entry Google is told to treat as non-canonical is a wasted
    crawl. Once the pages themselves disclaim nineteen of their twenty
    prefixes, the sitemap should stop advertising them too."""
    source = _strip_comments(_read(SITEMAP))

    solutions_block = re.search(
        r'\[.creators.,\s*.agencies.,\s*.filmmakers.,\s*.education.\]'
        r"\.map\(\(seg\)\s*=>\s*\((\{.*?\})\)\),",
        source,
        re.S,
    )
    assert solutions_block, "solutions route entry not found in sitemap.js"
    entry = solutions_block.group(1)

    assert re.search(r"locales:\s*\[\s*DEFAULT_LOCALE\s*\]", entry), (
        "the /solutions/* sitemap entry must set locales: [DEFAULT_LOCALE] -- "
        "without it, the sitemap lists 80 URLs for four pages that disclaim "
        "76 of them as non-canonical"
    )
