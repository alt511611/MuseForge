"""The home page FAQ answered four questions, and nobody asks any of them first.

Photo upload, demo mode, scene limits, ownership: questions about using the
product once you have picked it. The questions an assistant is actually put --
"what is MuseForge", "how does it keep characters consistent", "can it make a
series" -- had no answer on the page in the form an answer engine lifts: a
short, self-contained paragraph under the question it answers. Three were
added (faq_5..7) and moved to the front.

The list of keys now lives once, in client/lib/faq.js, because three places
render it: the accordion, the FAQPage JSON-LD and the Markdown edition. Google
drops an FAQ rich result whose markup names a question the page does not show,
and three hand-kept copies of `[1, 2, 3, 4]` are exactly how that happens.
"""

import os
import re

CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "client")
FAQ = os.path.join(CLIENT, "lib", "faq.js")
LOCALES = os.path.join(CLIENT, "lib", "i18n", "locales")

#: The three places the home FAQ is rendered.
READERS = (
    os.path.join(CLIENT, "app", "[locale]", "page.js"),
    os.path.join(CLIENT, "app", "[locale]", "HomeContent.js"),
    os.path.join(CLIENT, "lib", "content", "pages.js"),
)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _keys():
    m = re.search(r"HOME_FAQ_KEYS\s*=\s*\[([^\]]*)\]", _read(FAQ))
    assert m, "HOME_FAQ_KEYS not found in lib/faq.js"
    return [int(n) for n in re.findall(r"\d+", m.group(1))]


def test_every_place_that_renders_the_faq_reads_the_one_list():
    for path in READERS:
        source = _read(path)
        assert "HOME_FAQ_KEYS" in source, f"{path} does not read HOME_FAQ_KEYS"
        assert not re.search(r"\bfaq_[1-9]_q\b", source), (
            f"{path} names a FAQ key directly instead of iterating the list"
        )


def test_the_definitional_question_is_asked_first():
    """An answer engine takes the first matching answer it finds."""
    assert _keys()[0] == 5
    en = _read(os.path.join(LOCALES, "en.js"))
    assert re.search(r'faq_5_q: "What is MuseForge\?"', en)


def test_every_locale_answers_every_question_in_its_own_language():
    """A missing key falls back to English, which would put an English answer
    under a Turkish page's FAQPage markup -- schema in one language, page
    chrome in another."""
    keys = _keys()
    for name in sorted(os.listdir(LOCALES)):
        source = _read(os.path.join(LOCALES, name))
        for n in keys:
            for part in ("q", "a"):
                assert re.search(rf"^\s*faq_{n}_{part}:", source, re.M), (
                    f"{name} has no faq_{n}_{part}"
                )
