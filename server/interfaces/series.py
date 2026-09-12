"""The unit the market actually buys.

This product makes dramas. The thing distributors, platforms and studios buy
is a SERIES: sixty to ninety episodes of one story, commissioned as a block.
Everything here was already capable of making episode two -- the same faces
(the character library locks a portrait, a wardrobe and a voice), the same
room, the same look -- and nothing at all said that episode two IS the
continuation of episode one.

The gap is not cosmetic. Without it every episode is a pilot:

* the cliffhanger the screenwriter is told to end on (interfaces/micro_drama:
  "END ON THE QUESTION") is written into the result and then read by nothing.
  The one field whose entire purpose is to make someone open the next episode
  died with the job that produced it;
* episode two re-introduces its cast, re-establishes the room and re-explains
  the premise, because the only thing it was ever given was an idea and a
  scene count;
* nothing accumulates. Twelve episodes in, there is no record of what has
  happened, so scene one of episode twelve can contradict episode three and
  no part of the pipeline would know.

A SERIES OBJECT IS A MEMORY, NOT A FOLDER. What it carries is exactly what
episode N needs and cannot re-derive: the locked cast, the production locks
(language, ratio, look, setting), the story so far, and the question the last
frame left open. Grouping jobs under a title would have been a folder; this is
what makes the next script a continuation.

BOUNDED ON PURPOSE. A ninety-episode series cannot paste ninety synopses into
a prompt, and a screenwriter given all of them would write about the wrong
one. So the brief carries the last RECENT_EPISODES episodes in full and a
rolling summary of everything before them, which is how a writers' room works
and also the only shape that fits in a prompt at episode ninety.

NOTHING HERE COSTS A GENERATION. The synopsis is assembled from the script the
episode was already written from -- each scene's own "turn", which is the
field that says what changed -- rather than by asking a model to summarise
what a model just wrote.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

#: How many episodes are described in full to the writer of the next one.
#:
#: Three, because that is the span a viewer is actually holding: the episode
#: they just watched, and enough before it to know who is lying. Everything
#: earlier is in the rolling summary, where it stays true without competing
#: for the model's attention with the beat it has to write next.
RECENT_EPISODES = 3

#: Caps on the two blocks of prose this module generates. A brief is prepended
#: to every episode's script prompt, so it is paid for on every episode of
#: every series; these are the limits that keep episode ninety's prompt the
#: same size as episode two's.
SYNOPSIS_CHARS = 400
STORY_SO_FAR_CHARS = 1200

#: What a series defaults to when nothing says otherwise. Vertical, micro-drama
#: shaped -- because that is the format this is being sold into, and a series
#: of cinematic 16:9 shorts is a thing nobody is commissioning sixty of.
DEFAULT_ASPECT_RATIO = "9:16"
DEFAULT_NARRATIVE_MODE = "micro_drama"


@dataclass
class SeriesCharacter:
    """One member of the recurring cast, locked across every episode.

    The same four things the character library stores, for the same reason it
    stores them: the portrait binds a face, the wardrobe binds an outfit the
    portrait cannot, the voice binds who is speaking, and the description is
    what the screenwriter is handed so it does not invent a fifth version of
    this person in episode nine.
    """

    name: str
    description: str = ""
    wardrobe: str = ""
    portrait_url: str = ""
    voice_id: str = ""

    def as_dict(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "description": self.description,
            "wardrobe": self.wardrobe,
            "portrait_url": self.portrait_url,
            "voice_id": self.voice_id,
        }

    def as_preset(self) -> Dict[str, str]:
        """The shape every existing caller already speaks.

        ``preset_characters`` reaches the screenwriter, the portrait lock and
        the voice casting untouched -- so a series needs no new machinery in
        any of them, only a place for the decisions to live between episodes.
        """
        return {
            "name": self.name,
            "static_features": self.description,
            "portrait_url": self.portrait_url,
            "voice_id": self.voice_id,
            "wardrobe": self.wardrobe,
        }


@dataclass
class Episode:
    """One delivered episode, as the series remembers it."""

    number: int
    job_id: str = ""
    title: str = ""
    logline: str = ""
    synopsis: str = ""
    cliffhanger: str = ""
    video_url: str = ""
    status: str = "queued"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "job_id": self.job_id,
            "title": self.title,
            "logline": self.logline,
            "synopsis": self.synopsis,
            "cliffhanger": self.cliffhanger,
            "video_url": self.video_url,
            "status": self.status,
        }


@dataclass
class Series:
    """A story that continues, and everything episode N+1 needs to continue it."""

    id: str = ""
    title: str = ""
    premise: str = ""
    #: Production locks. Every episode of a series is made the same way -- a
    #: season that changes aspect ratio or language halfway through is not a
    #: season -- so these are properties of the SERIES and the per-episode
    #: request does not get to argue with them.
    language: str = "en"
    aspect_ratio: str = DEFAULT_ASPECT_RATIO
    narrative_mode: str = DEFAULT_NARRATIVE_MODE
    director_style: str = "cinematic_balanced"
    style: str = "Cinematic"
    num_scenes: int = 3
    delivery_tier: str = ""
    setting_location: str = ""
    setting_time_of_day: str = ""
    setting_era: str = ""
    theme: str = ""
    visual_motif: str = ""
    #: The recurring cast, in ORDER. The order is load-bearing: it decides the
    #: 180-degree axis every frame prompt states (frame-left, frame-right) and
    #: therefore which side of the screen each character lives on -- for the
    #: whole series, not just one episode. See script2video.
    #: build_screen_direction_clause and interfaces/reframe.
    cast: List[SeriesCharacter] = field(default_factory=list)
    episodes: List[Episode] = field(default_factory=list)
    #: Everything before the last RECENT_EPISODES, rolled into one paragraph.
    story_so_far: str = ""
    #: The question the most recent episode's last frame left open. This is
    #: the one the next episode opens on, and it is the field that was being
    #: written and never read.
    open_question: str = ""

    # --- reading -----------------------------------------------------------

    @property
    def next_number(self) -> int:
        """The episode about to be made. One-based, like an episode number."""
        return max((e.number for e in self.episodes), default=0) + 1

    @property
    def delivered(self) -> List[Episode]:
        return [e for e in self.episodes if e.status == "completed"]

    def episode(self, number: int) -> Optional[Episode]:
        return next((e for e in self.episodes if e.number == number), None)

    def preset_characters(self) -> List[Dict[str, str]]:
        """The cast, in the shape /api/generate and the pipeline already take.

        Only members whose face is actually locked: a character with no
        portrait is a name the screenwriter would be told to reuse and the
        renderer would then invent from scratch, which is the drift a series
        exists to prevent, arrived at by a different route.
        """
        return [c.as_preset() for c in self.cast if c.portrait_url and c.description]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "premise": self.premise,
            "language": self.language,
            "aspect_ratio": self.aspect_ratio,
            "narrative_mode": self.narrative_mode,
            "director_style": self.director_style,
            "style": self.style,
            "num_scenes": self.num_scenes,
            "delivery_tier": self.delivery_tier,
            "setting_location": self.setting_location,
            "setting_time_of_day": self.setting_time_of_day,
            "setting_era": self.setting_era,
            "theme": self.theme,
            "visual_motif": self.visual_motif,
            "cast": [c.as_dict() for c in self.cast],
            "episodes": [e.as_dict() for e in self.episodes],
            "story_so_far": self.story_so_far,
            "open_question": self.open_question,
            "episode_count": len(self.episodes),
            "next_episode": self.next_number,
        }


def from_dict(data: Mapping[str, Any]) -> Series:
    """A Series from stored JSON, tolerating everything that might be missing.

    Every field has a default and nothing raises: a row written by an older
    build, or by hand, must still produce a series that can commission its
    next episode.
    """
    data = data or {}
    series = Series(
        id=str(data.get("id") or ""),
        title=str(data.get("title") or ""),
        premise=str(data.get("premise") or ""),
        language=str(data.get("language") or "en"),
        aspect_ratio=str(data.get("aspect_ratio") or DEFAULT_ASPECT_RATIO),
        narrative_mode=str(data.get("narrative_mode") or DEFAULT_NARRATIVE_MODE),
        director_style=str(data.get("director_style") or "cinematic_balanced"),
        style=str(data.get("style") or "Cinematic"),
        num_scenes=int(data.get("num_scenes") or 3),
        delivery_tier=str(data.get("delivery_tier") or ""),
        setting_location=str(data.get("setting_location") or ""),
        setting_time_of_day=str(data.get("setting_time_of_day") or ""),
        setting_era=str(data.get("setting_era") or ""),
        theme=str(data.get("theme") or ""),
        visual_motif=str(data.get("visual_motif") or ""),
        story_so_far=str(data.get("story_so_far") or ""),
        open_question=str(data.get("open_question") or ""),
    )
    for entry in data.get("cast") or []:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        series.cast.append(
            SeriesCharacter(
                name=name,
                description=str(
                    entry.get("description") or entry.get("static_features") or ""
                ),
                wardrobe=str(entry.get("wardrobe") or ""),
                portrait_url=str(entry.get("portrait_url") or ""),
                voice_id=str(entry.get("voice_id") or ""),
            )
        )
    for entry in data.get("episodes") or []:
        if not isinstance(entry, Mapping):
            continue
        try:
            number = int(entry.get("number"))
        except (TypeError, ValueError):
            continue
        series.episodes.append(
            Episode(
                number=number,
                job_id=str(entry.get("job_id") or ""),
                title=str(entry.get("title") or ""),
                logline=str(entry.get("logline") or ""),
                synopsis=str(entry.get("synopsis") or ""),
                cliffhanger=str(entry.get("cliffhanger") or ""),
                video_url=str(entry.get("video_url") or ""),
                status=str(entry.get("status") or "queued"),
            )
        )
    series.episodes.sort(key=lambda e: e.number)
    return series


# --- what an episode leaves behind -----------------------------------------


def _clip(text: str, limit: int) -> str:
    """Cut prose to a length without cutting a word in half."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:.")
    return f"{cut}…"


def synopsis_of(script: Mapping[str, Any]) -> str:
    """What happened in this episode, from the script it was made from.

    Assembled from each scene's ``turn`` -- the field that says what CHANGES
    in that scene, and the most load-bearing one the screenwriter writes --
    falling back to the action line where a scene has no turn. Deterministic
    and free: asking a model to summarise a script another model just wrote
    costs a call, takes a minute, and produces a paraphrase of prose we are
    holding.
    """
    beats: List[str] = []
    for scene in (script or {}).get("scenes") or []:
        if isinstance(scene, str):
            beats.append(scene)
            continue
        if not isinstance(scene, Mapping):
            continue
        beat = str(scene.get("turn") or "").strip() or str(
            scene.get("action") or ""
        ).strip()
        if beat:
            beats.append(beat)
    return _clip(" ".join(beats), SYNOPSIS_CHARS)


def cast_from_result(result: Mapping[str, Any]) -> List[SeriesCharacter]:
    """The cast a finished episode locked, ready to be re-used by the next.

    Reads the three records the render already writes: the script's characters
    (name, description, wardrobe), ``portraits`` (the locked face, generated
    once) and ``character_voices`` (who was cast with which voice). The last
    one matters more than it looks: voice casting is a hash of the NAME that
    walks past voices already taken, so adding one character to episode two
    re-casts the returning lead unless the decision is written down.
    """
    script = (result or {}).get("script") or {}
    portraits = (result or {}).get("portraits") or {}
    voices = (result or {}).get("character_voices") or {}
    cast: List[SeriesCharacter] = []
    for entry in script.get("characters") or []:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        cast.append(
            SeriesCharacter(
                name=name,
                description=str(entry.get("description") or ""),
                wardrobe=str(entry.get("wardrobe") or ""),
                portrait_url=str(portraits.get(name) or ""),
                voice_id=str(voices.get(name) or ""),
            )
        )
    return cast


def _merged_cast(
    existing: Sequence[SeriesCharacter], arriving: Sequence[SeriesCharacter]
) -> List[SeriesCharacter]:
    """The series cast after an episode, keeping the ORDER it already had.

    Order is the 180-degree axis (see Series.cast), so a returning character
    must keep their position or the whole series flips sides at episode four.
    A returning character fills in only what the series did not have -- the
    lock the series holds outranks whatever this episode happened to
    re-generate -- and a new one joins at the end.
    """
    merged = [
        SeriesCharacter(
            c.name, c.description, c.wardrobe, c.portrait_url, c.voice_id
        )
        for c in existing
    ]
    by_name = {c.name.casefold(): c for c in merged}
    for character in arriving:
        held = by_name.get(character.name.casefold())
        if held is None:
            merged.append(character)
            by_name[character.name.casefold()] = character
            continue
        held.description = held.description or character.description
        held.wardrobe = held.wardrobe or character.wardrobe
        held.portrait_url = held.portrait_url or character.portrait_url
        held.voice_id = held.voice_id or character.voice_id
    return merged


def absorb(series: Series, number: int, job_id: str, result: Mapping[str, Any]) -> Series:
    """Fold a finished episode into the series it belongs to.

    Four things move: the episode's own record, the cast (whatever it locked
    that the series did not already hold), the open question (this episode's
    cliffhanger, which is the next one's opening), and -- once an episode
    falls out of the recent window -- the rolling summary.

    The series' production locks are NOT updated from the episode. They are
    what the episode was made under; letting a render write back to them would
    make a drifting episode redefine the series it drifted from.
    """
    script = (result or {}).get("script") or {}
    episode = series.episode(number) or Episode(number=number)
    episode.job_id = job_id or episode.job_id
    episode.title = str(script.get("title") or episode.title)
    episode.logline = str(script.get("logline") or episode.logline)
    episode.synopsis = synopsis_of(script) or episode.synopsis
    episode.cliffhanger = str(script.get("cliffhanger") or episode.cliffhanger)
    episode.video_url = str((result or {}).get("video_url") or episode.video_url)
    episode.status = "completed"
    if series.episode(number) is None:
        series.episodes.append(episode)
    series.episodes.sort(key=lambda e: e.number)

    series.cast = _merged_cast(series.cast, cast_from_result(result))

    # The setting is locked by the FIRST episode that establishes one, and
    # never moved afterwards: "the same room" is most of what makes a set of
    # films a series.
    series.setting_location = series.setting_location or str(
        script.get("setting_location") or ""
    )
    series.setting_time_of_day = series.setting_time_of_day or str(
        script.get("setting_time_of_day") or ""
    )
    series.setting_era = series.setting_era or str(script.get("setting_era") or "")
    series.theme = series.theme or str(script.get("theme") or "")
    series.visual_motif = series.visual_motif or str(script.get("visual_motif") or "")

    # The last frame's question, which is what the next episode opens on. A
    # cinematic episode resolves and leaves none, and then the next one opens
    # on the story rather than on a hook -- which is correct for that mode.
    series.open_question = episode.cliffhanger or series.open_question
    series.story_so_far = _rolled_up(series)
    return series


def _rolled_up(series: Series) -> str:
    """Everything before the recent window, as one paragraph.

    Grown by APPENDING each episode as it ages out, rather than by
    re-summarising the whole series every time: a summary of a summary loses a
    name per pass, and by episode forty the protagonist has a different one.
    Capped at STORY_SO_FAR_CHARS from the END, because a series that has run
    that long is answerable to its recent past first.
    """
    delivered = series.delivered
    aged_out = delivered[: max(0, len(delivered) - RECENT_EPISODES)]
    if not aged_out:
        return series.story_so_far
    sentences = [
        f"Ep {episode.number}: {episode.synopsis}"
        for episode in aged_out
        if episode.synopsis
    ]
    joined = " ".join(sentences)
    if len(joined) <= STORY_SO_FAR_CHARS:
        return joined
    return "…" + joined[-STORY_SO_FAR_CHARS:].split(" ", 1)[-1]


# --- what the next episode is told -----------------------------------------


def continuity_brief(series: Series) -> str:
    """The block handed to the screenwriter before it writes episode N.

    Facts, not rules: who exists, what has happened, what is still open. The
    rules live in SCREENWRITER_CLAUSE, which goes in the system prompt where a
    model weighs it as instruction rather than as material.

    Empty for episode one, which has no continuity to carry and should be
    written exactly as a standalone drama is -- it IS one, until it has a
    sequel.
    """
    number = series.next_number
    if number <= 1:
        return ""

    lines = [
        f"SERIES: {series.title}".strip(),
        f"THIS IS EPISODE {number}. It continues the story below; it does not "
        "restart it.",
    ]
    if series.premise:
        lines.append(f"Premise: {series.premise}")
    if series.story_so_far:
        lines.append(f"Earlier episodes: {series.story_so_far}")

    recent = series.delivered[-RECENT_EPISODES:]
    for episode in recent:
        summary = episode.synopsis or episode.logline
        if summary:
            lines.append(f"Episode {episode.number}: {summary}")
    if series.open_question:
        lines.append(
            "THE LAST FRAME OF THE PREVIOUS EPISODE LEFT THIS OPEN: "
            f"{series.open_question}"
        )
    if series.cast:
        known = "; ".join(
            f"{c.name} — {c.description}" + (f" (wears {c.wardrobe})" if c.wardrobe else "")
            for c in series.cast
            if c.description
        )
        if known:
            lines.append(f"Established cast (already known to the viewer): {known}")
    setting = ", ".join(
        part
        for part in (
            series.setting_location,
            series.setting_time_of_day,
            series.setting_era,
        )
        if part
    )
    if setting:
        lines.append(f"Established setting: {setting}")
    if series.theme:
        lines.append(f"The series argues: {series.theme}")
    if series.visual_motif:
        lines.append(f"Recurring visual motif: {series.visual_motif}")
    return "\n".join(line for line in lines if line.strip())


#: Appended to the screenwriter's system prompt for any episode after the
#: first.
#:
#: It exists to CONTRADICT the instinct a fresh prompt produces -- introduce
#: the people, establish the place, set up the situation -- because the viewer
#: of episode nine has met these people eight times and an episode that
#: introduces them again is an episode they close. Placed last, like the
#: micro-drama clause, where a model weighs it against what came before.
SCREENWRITER_CLAUSE = """

THIS IS NOT A PILOT. You are writing one episode of a series that is already
running, and the rules above about introducing a world are REPLACED by these:

DO NOT RE-INTRODUCE ANYONE. The established cast listed in the brief are known
to the viewer. Do not describe them as if they were new, do not restate their
relationship, and do not give them an introductory beat. Use their names in
the first line as if the audience already knows them, because they do.

OPEN ON THE CONSEQUENCE. The previous episode's last frame left a question
open and the brief names it. Scene 1 is what HAPPENS NEXT because of it — not
a recap, not a flashback, not a character explaining events the viewer just
watched. Write no "previously on"; the platform plays the episodes in order.

DO NOT ANSWER THE SERIES. Resolve enough of this episode's own beat to make it
worth watching, and leave the series' question open — including the one you
inherit. Your last scene ends on a NEW open question, written into
"cliffhanger", so the next episode has somewhere to start.

CONTINUITY IS BINDING. Nothing in the brief may be contradicted: the cast's
descriptions, the setting, the motif and what has already happened are facts
of this world, not suggestions. If your idea for this episode needs one of
them to be different, the idea is wrong, not the record."""
