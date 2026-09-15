"""Every address and URL the site publishes must be on the domain it serves.

This repo has already paid for this mistake once, at the worst possible scale.
`NEXT_PUBLIC_SITE_URL` was unset in production and the code fell back to
museforge.ai -- a different, parked domain -- so every canonical tag, every
hreflang annotation and all 169 sitemap entries told Google the real copy of
each page lived somewhere else. The somewhere else was empty. Nothing on the
site was indexed. lib/seo.js carries the note.

The fallback was fixed. The CONTACT ADDRESSES were not: the enterprise sales
link on /pricing, the enterprise CTA on /solutions/education, and the two legal
contacts still pointed at @museforge.ai long afterwards. That is the same bug
with a quieter failure -- an enterprise enquiry that bounces leaves no trace in
Search Console, or anywhere else, because the person who sent it simply never
hears back.

So the rule is checked rather than remembered: no client source file may
publish an address or a link on a domain this site does not serve. The two
historical mentions in comments are exempt by construction -- they are prose
about the incident, and a test that forbade naming the domain would delete the
explanation of why it matters.
"""

import os
import re

import pytest

CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "client")

#: The host the site is actually served from -- the production fallback in
#: client/lib/seo.js, which is where the canonical URLs come from.
CANONICAL_HOST = "museforge.studio"

#: Domains that were once used and are not served. Naming them in a comment is
#: fine; publishing a mailto: or an href to one is not.
DEAD_DOMAINS = ("museforge.ai",)

SKIP_DIRS = {"node_modules", ".next", ".git", "out", "build"}


def _client_sources():
    for root, dirs, files in os.walk(CLIENT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.endswith((".js", ".jsx", ".ts", ".tsx")):
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as f:
                    yield os.path.relpath(path, CLIENT), f.read()


def _published_references(source, domain):
    """Occurrences of `domain` that a browser would actually act on.

    A mailto:, an href, or a bare address inside a rendered string. Comments
    are not included: the incident is documented in two of them, and the
    documentation is the reason anybody knows to keep this test.
    """
    without_comments = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    without_comments = re.sub(r"(?<!:)//[^\n]*", " ", without_comments)
    pattern = rf"(mailto:[^\s\"']*{re.escape(domain)}|https?://[^\s\"']*{re.escape(domain)}|[\w.+-]+@{re.escape(domain)})"
    return re.findall(pattern, without_comments)


@pytest.mark.parametrize("domain", DEAD_DOMAINS)
def test_no_page_publishes_a_link_or_address_on_a_domain_we_do_not_serve(domain):
    offenders = []
    for path, source in _client_sources():
        for hit in _published_references(source, domain):
            offenders.append(f"{path}: {hit}")
    assert not offenders, (
        f"{domain} is not served by this site; these would bounce or 404:\n  "
        + "\n  ".join(offenders)
    )


def test_the_contact_addresses_are_on_the_canonical_host():
    """The positive half. The test above passes if every address is deleted,
    which would also be wrong -- an enterprise plan with no way to contact
    sales is not an improvement on one that bounces."""
    found = set()
    for _path, source in _client_sources():
        found.update(re.findall(rf"mailto:([\w.+-]+@{re.escape(CANONICAL_HOST)})", source))

    for expected in ("enterprise", "legal", "privacy"):
        assert any(a.startswith(f"{expected}@") for a in found), (
            f"no {expected}@{CANONICAL_HOST} contact link found in the client"
        )


def test_the_canonical_host_is_still_what_seo_js_falls_back_to():
    """This file's whole premise is that CANONICAL_HOST is the served domain.
    If the fallback in seo.js moves, the checks above start policing the wrong
    name and pass while meaning nothing."""
    with open(os.path.join(CLIENT, "lib", "seo.js"), encoding="utf-8") as f:
        assert f'"https://www.{CANONICAL_HOST}"' in f.read()
