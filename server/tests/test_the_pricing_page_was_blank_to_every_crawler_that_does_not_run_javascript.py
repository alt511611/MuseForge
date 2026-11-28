"""/pricing prerendered as a navbar and nothing else, in all twenty locales.

OpenSEO's crawl of museforge.studio on 2026-10-08 counted two words and no H1
on /pricing and on every one of its nineteen translations -- the only page
family on the site where that happened. The cause was one line at the top of
PricingContent: `useSearchParams()`, read to show a banner after checkout.

In a statically prerendered page, that hook makes Next abandon server
rendering up to the nearest Suspense boundary, and the nearest boundary was
the one wrapping the entire page with `fallback={null}`. So the HTML a crawler
receives was the fallback: nothing. Googlebot renders JavaScript and eventually
saw the plans. GPTBot, ClaudeBot and PerplexityBot do not render it, so the
page that answers "how much does MuseForge cost" was empty to every assistant
asked -- while the Product JSON-LD beside it promised prices the page did not
visibly carry.

The fix moves the hook into CheckoutSuccess, a banner with its own Suspense
boundary. After it, the prerendered en/pricing.html carries 477 words and its
H1. These tests keep the hook fenced in: there is no JS runner in this repo, so
like the rest of the client-side suite they read the source for the shape of
the mistake.
"""

import os
import re

CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "client")
PRICING = os.path.join(CLIENT, "app", "[locale]", "pricing", "PricingContent.js")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _strip_comments(source):
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*", " ", source)


def _functions(source):
    """Top-level `function Name(` bodies, keyed by name. Brace-counted, which
    is enough for this file: no braces inside strings at the top level."""
    out = {}
    for m in re.finditer(r"^(?:export default )?function (\w+)\s*\(", source, re.M):
        start = source.index("{", m.end())
        depth, i = 0, start
        while True:
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out[m.group(1)] = source[start : i + 1]
    return out


def test_only_the_checkout_banner_reads_the_query_string():
    """Every call to useSearchParams lives in CheckoutSuccess. One anywhere
    else -- the plans, the FAQ, the page component -- is the whole page going
    back to client-only rendering."""
    fns = _functions(_strip_comments(_read(PRICING)))
    callers = sorted(name for name, body in fns.items() if "useSearchParams(" in body)
    assert callers == ["CheckoutSuccess"], callers


def test_the_checkout_banner_has_a_boundary_of_its_own():
    """CheckoutSuccess bails out to its nearest Suspense. If that is not a
    boundary directly around it, the nearest one is the page's, and the plans
    go with it."""
    fns = _functions(_strip_comments(_read(PRICING)))
    main = fns["PricingContent"]
    assert re.search(r"<Suspense[^>]*>\s*<CheckoutSuccess\s*/>\s*</Suspense>", main), (
        "CheckoutSuccess is rendered without a Suspense boundary of its own"
    )
