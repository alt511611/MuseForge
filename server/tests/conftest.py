"""What the suite is allowed to see of the machine it runs on.

`api.py` calls `load_dotenv()` at import time, which is right for a server and
wrong for a test process: the first test that imports the API module hands the
developer's real `.env` to every test that runs after it. The variables in that
file are not decoration -- they are the vendor selectors, so a suite that reads
them is not testing the shipped defaults at all. It runs whatever the laptop is
pointed at that week, and it runs it differently depending on which test
happened to import `api` first.

That is not a hypothetical. On this machine `.env` carries
MUSEFORGE_IMAGE_PROVIDER=falai, and the consequence was forty failures that
every one of them passed in isolation -- `test_cancellation` monkeypatched the
MuAPI image generator, the pipeline resolved fal.ai instead, and the call went
to `queue.fal.run` and came back 401. Tests were reaching a paid third-party
API over the network, at whatever it costs when the key is not expired. CI
never saw any of it, because a checkout has no `.env`.

So the environment is pinned here, once, before collection: the suite sees the
same variables on a laptop as it does on a runner, and `_no_outbound_network`
below makes sure that if a selector ever escapes this list again it fails
loudly on the first socket instead of quietly on the first invoice.
"""

from __future__ import annotations

import os
import socket

import pytest

#: Every variable the server reads that a developer's `.env` may set. Cleared
#: before collection, so a test observes the shipped default unless it sets one
#: itself with `monkeypatch.setenv` -- which is scoped, and undone afterwards.
#:
#: Grouped by what a leak actually costs, because the three groups fail
#: differently and only the first one is obvious:
_LEAKY_ENV = (
    # Vendor selectors. A leak sends the stage to a backend the test did not
    # patch, so the test's double is never called and the real client is.
    "MUSEFORGE_IMAGE_PROVIDER",
    "MUSEFORGE_VIDEO_PROVIDER",
    "MUSEFORGE_VOICE_PROVIDER",
    "MUSEFORGE_LIPSYNC_PROVIDER",
    "MUSEFORGE_SFX_PROVIDER",
    "MUSEFORGE_MUSIC_PROVIDER",
    # Credentials. A leak turns "this fails cleanly without a key" into a live
    # request, and turns a green test into a bill.
    "MUAPI_KEY",
    "MUAPI_BASE",
    "FAL_KEY",
    "FAL_KEY_ID",
    "FAL_KEY_SECRET",
    "ELEVENLABS_API_KEY",
    "ANTHROPIC_API_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    # Model and behaviour overrides. A leak is the quietest of the three: the
    # code under test runs, and asserts about a default that is no longer the
    # default. `MUSEFORGE_SECONDS_PER_SCENE` alone moves the length of every
    # film the suite measures.
    "MUAPI_IMAGE_MODEL",
    "MUAPI_LIPSYNC_MODEL",
    "MUAPI_LLM_MODEL",
    "MUAPI_MUSIC_MODEL",
    "MUAPI_SFX_MODEL",
    "FALAI_IMAGE_MODEL",
    "FALAI_LIPSYNC_MODEL",
    "FALAI_LIPSYNC_QUALITY",
    "FALAI_LIPSYNC_SYNC_MODE",
    "FALAI_MUSIC_MODEL",
    "FALAI_SFX_MODEL",
    "ELEVENLABS_DIALOGUE_MODEL",
    "MUSEFORGE_EDIT_MODEL",
    "MUSEFORGE_DIALOGUE_ENABLED",
    "MUSEFORGE_LIPSYNC_ENABLED",
    "MUSEFORGE_FOLEY",
    "MUSEFORGE_WORD_CAPTIONS",
    "MUSEFORGE_SPEAKER_LABELS",
    "MUSEFORGE_FINISHING",
    "MUSEFORGE_FILM_GRAIN",
    "MUSEFORGE_GRADE_STRENGTH",
    "MUSEFORGE_SCENE_TRANSITIONS",
    "MUSEFORGE_NARRATIVE_MODE",
    "MUSEFORGE_CHARACTER_QA_ENABLED",
    "MUSEFORGE_DYNAMIC_REFERENCE",
    "MUSEFORGE_KLING_NATIVE_AUDIO",
    "MUSEFORGE_EXACT_RESOLUTION",
    "MUSEFORGE_SECONDS_PER_SCENE",
    "MUSEFORGE_SHOTS_PER_SCENE",
    "MUSEFORGE_TARGET_FPS",
    "MUSEFORGE_IMAGE_WIDTH",
    "MUSEFORGE_IMAGE_HEIGHT",
    "MUSEFORGE_GENERATION_RETRIES",
    "MUSEFORGE_JOBS_DIR",
    "MUSEFORGE_DEMO",
    "MUSEFORGE_DEMO_VIDEO",
    "MUSEFORGE_STORAGE_BUCKET",
    "MUSEFORGE_STORAGE_RETENTION",
    "MUSEFORGE_LOCAL_LIPSYNC_URL",
)


def pytest_configure(config):
    """Shut the door before a single test module is imported.

    A fixture would be too late for anything a module decides at import time,
    and several of them do -- `auth.py` and `jobs.py` turn environment
    variables into module-level constants the moment they are imported.

    Two things happen here, and both are needed. Clearing the variables is not
    enough on its own, because `api.py` calls `load_dotenv()` when it is
    imported, which is after this hook runs: the file would simply be read
    back in over the top of the cleared values. So `load_dotenv` is neutered
    first, and the clear then holds for the rest of the session.
    """
    import dotenv

    def _refuse_dotenv(*_args, **_kwargs) -> bool:
        """The server reads `.env`. The test process does not."""
        return False

    dotenv.load_dotenv = _refuse_dotenv
    # `api.py` binds the name with `from dotenv import load_dotenv`, but it
    # does so when IT is imported, which is after this. Patching the module
    # attribute is therefore enough, and it also covers any future caller.
    if hasattr(dotenv, "main"):
        dotenv.main.load_dotenv = _refuse_dotenv

    for name in _LEAKY_ENV:
        os.environ.pop(name, None)


@pytest.fixture(autouse=True)
def _no_outbound_network(monkeypatch, request):
    """Fail loudly on any socket that leaves this machine.

    The list above is a list, and a list goes stale the next time a selector is
    added. This is the backstop that does not: a test that reaches a vendor
    gets an error naming the address it tried, in the test that tried it,
    rather than a 401 traceback from inside a client library three frames deep.

    Loopback and unix sockets stay open -- the suite starts local servers.
    A test that genuinely needs the internet marks itself `@pytest.mark.network`.
    """
    if request.node.get_closest_marker("network"):
        return

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _local(address) -> bool:
        if not isinstance(address, tuple) or not address:
            return True  # AF_UNIX and friends: not the internet.
        host = str(address[0])
        return host in ("127.0.0.1", "::1", "localhost", "0.0.0.0", "")

    def guard(fn):
        def wrapper(self, address, *args, **kwargs):
            if not _local(address):
                raise RuntimeError(
                    f"Test tried to open a network connection to {address!r}. "
                    "Nothing in this suite is allowed to reach a vendor: patch "
                    "the client, or mark the test @pytest.mark.network."
                )
            return fn(self, address, *args, **kwargs)
        return wrapper

    monkeypatch.setattr(socket.socket, "connect", guard(real_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guard(real_connect_ex))
