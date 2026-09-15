"""A page renders its body once, and declares its breadcrumb trail once.

THIS REPO LOSES THIS FIGHT REPEATEDLY. ae1a495 says it out loud -- "main
shipped both copies of a function it had just replaced, for the third time" --
and the branch this test arrives on is named after the mechanism: a squashed
branch merged twice keeps both copies. The refactor lands, the same work lands
again through a second path, and the merge resolves by keeping everything.
Nothing fails to compile, so nothing complains.

It happened again in 82a92ad, on the client this time. That commit was the
mailto fix; 53f0525 had just moved the four solution pages' copy out into
content.js. The merge kept both EducationPage bodies. The live one reads
CONTENT and t(); the stale one is the pre-refactor hardcoded English, and it
was still being rendered above the real one for every visitor, at every locale,
with its own <JsonLd graph={[breadcrumbSchema(TRAIL)]} /> above that.

The duplicated markup is the visible half and the cheaper half. The expensive
half is the structured data: two breadcrumb graphs on one page is two
competing declarations of where that page sits, sent to the same crawler that
7d6ea94 and 82a92ad were spent getting to read this site correctly at all. A
page cannot have two positions in a hierarchy, so the one it gets is whichever
the parser prefers.

Hence the shape of the check. It does not diff the pages against each other --
they are allowed to differ, that is the point of four segment pages. It counts
DECLARATIONS, because a second copy of a page body cannot be added without
also adding a second copy of the one element that is supposed to be unique.
"""

import os
import re

import pytest

CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "client")
APP = os.path.join(CLIENT, "app")
SOLUTIONS = os.path.join(APP, "[locale]", "solutions")

SKIP_DIRS = {"node_modules", ".next", ".git", "out", "build"}

#: The segments that each have a page under app/[locale]/solutions.
SEGMENTS = ("agencies", "creators", "education", "filmmakers")


def _strip_comments(source):
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*", " ", source)


def _page_modules():
    """Every route module under client/app, as (relative path, source)."""
    for root, dirs, files in os.walk(APP):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if not name.endswith((".js", ".jsx", ".ts", ".tsx")):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as f:
                yield os.path.relpath(path, CLIENT), _strip_comments(f.read())


def _count(source, component):
    return len(re.findall(rf"<{component}[\s/>]", source))


def test_no_route_module_emits_more_than_one_json_ld_graph():
    """One page, one structured-data declaration.

    Every module that emits JSON-LD today emits exactly one <JsonLd>, and a
    second one has never been deliberate -- it has only ever meant a page body
    that survived a merge twice. If a page ever legitimately needs two graphs,
    they belong in the one `graph={[...]}` array, which is what the prop is
    shaped for, rather than in a second element.
    """
    offenders = [
        f"{path}: {n} <JsonLd> elements"
        for path, source in _page_modules()
        if (n := _count(source, "JsonLd")) > 1
    ]
    assert not offenders, (
        "a page with two JSON-LD blocks tells the crawler two different things "
        "about itself; keep one:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("segment", SEGMENTS)
def test_a_solution_page_renders_one_solution_page(segment):
    """The visible half of the same failure.

    The stale education body was not a stray tag -- it was a whole second
    <SolutionPage ...> with seventy lines of hardcoded English props, rendered
    above the real one. Counting the component catches the copy even when the
    two copies say different things, which is exactly the case a diff of the
    four pages would miss.
    """
    path = os.path.join(SOLUTIONS, segment, "page.js")
    with open(path, encoding="utf-8") as f:
        source = _strip_comments(f.read())

    assert _count(source, "SolutionPage") == 1, (
        f"solutions/{segment}/page.js renders <SolutionPage> more than once -- "
        "the page body is in there twice"
    )
    assert _count(source, "Breadcrumbs") == 1, (
        f"solutions/{segment}/page.js renders <Breadcrumbs> more than once"
    )


@pytest.mark.parametrize("segment", SEGMENTS)
def test_a_solution_page_reads_its_copy_from_content_js(segment):
    """The positive half, and the reason the stale copy was the stale one.

    53f0525 moved the words into content.js so the Markdown edition at
    /md/<locale>/solutions/<segment> renders the same words as the HTML page --
    two renderers over one object, which is the only arrangement in which the
    machine-readable copy cannot say something the page does not. A page that
    renders hardcoded props instead has quietly opted out of that guarantee,
    which is the state education was left in above the fold.
    """
    path = os.path.join(SOLUTIONS, segment, "page.js")
    with open(path, encoding="utf-8") as f:
        source = _strip_comments(f.read())

    for prop in ("subheading", "differentiators", "planCard", "ctaBanner"):
        assert re.search(rf"{prop}=\{{CONTENT\.{prop}\}}", source), (
            f"solutions/{segment}/page.js does not take `{prop}` from CONTENT; "
            "the Markdown edition of this page would say something else"
        )
