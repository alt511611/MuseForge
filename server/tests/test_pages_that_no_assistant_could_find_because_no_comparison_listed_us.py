"""Four assistants were asked for the best AI movie maker and named none of ours.

On 2026-11-28 ChatGPT, Claude, Gemini and Perplexity were each asked for the
best AI movie maker for a short film with consistent characters. Every answer
was assembled from third-party roundups and vendor pages; MuseForge was on
none of them. An assistant recommends what it can find compared, so the site
now carries its own comparison and a Q&A page built from the questions people
actually ask, and the IndexNow key that lets Bing-fed assistants hear about
both the day they ship.
"""

import os
import re

CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "client")
BLOG = os.path.join(CLIENT, "content", "blog")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def test_the_comparison_and_the_questions_are_registered_as_articles():
    index = _read(CLIENT, "lib", "content", "index.js")
    for slug in ("best-ai-short-film-makers", "ai-movie-maker-questions"):
        assert os.path.isdir(os.path.join(BLOG, slug))
        assert f"content/blog/{slug}" in index, f"{slug} is not imported"
    arr = index.split("export const ARTICLES = [", 1)[1].split("]", 1)[0]
    assert "bestShortFilmMakers" in arr and "movieMakerQuestions" in arr


def test_every_question_in_a_faq_block_is_answered_in_a_sentence_that_stands_alone():
    for slug in ("best-ai-short-film-makers", "ai-movie-maker-questions"):
        src = _read(BLOG, slug, "en.js")
        pairs = re.findall(r'q: "([^"]+)",\s*a: "((?:[^"\\]|\\.)+)"', src)
        assert pairs, f"{slug} has no FAQ pairs"
        for q, a in pairs:
            assert q.endswith("?"), q
            assert len(a) > 80, f"answer to {q!r} is too thin to be quoted"


def test_the_indexnow_key_is_served_from_public_and_exempt_from_locale_rewrites():
    public = os.path.join(CLIENT, "public")
    keys = [f for f in os.listdir(public) if re.fullmatch(r"[0-9a-f]{32}\.txt", f)]
    assert len(keys) == 1
    assert _read(public, keys[0]).strip() == keys[0][:-4]
    assert r"[0-9a-f]{32}\\.txt" in _read(CLIENT, "middleware.js")
