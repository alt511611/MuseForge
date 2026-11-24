"""Job e85c3f62: Mira looked straight into the lens in every lip-synced wide.

The writer's rule is that no character plays to the lens. The frame prompt for
a lip-synced shot said the speaking mouth was "facing camera" -- while another
clause of the same prompt says the eyes never go to the lens -- and the image
model does what it is told: the scene's first frame -- which the lip-sync pass
redraws the whole take from -- was a woman staring down the lens, and so was
the take.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import inspect

from pipelines import script2video


def test_the_speaking_mouth_clause_does_not_order_the_face_at_the_lens():
    source = inspect.getsource(script2video)
    start = source.index("elif lipsync_enabled:")
    clause = source[start:start + 900]
    assert "facing camera" not in clause
    # what the sync pass needs is unchanged
    assert "fully visible" in clause and "lips will be animated" in clause
