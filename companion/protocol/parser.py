"""Raw JSON dict -> normalized events. INTENTIONALLY A STUB.

Field-name mappings here must come from running tools/capture_spike.py against your own live
AQW traffic (Step 0 in the project plan), not transcribed from any third party's unlicensed
reverse-engineering notes -- both for legal cleanliness and because the protocol drifts (the
known reference port list, 5588 vs 5594, already disagrees with itself).

Until that spike is run and this module filled in, parse_frame always returns [], so the rest
of the pipeline (capture -> reassemble -> bridge -> state -> rules -> overlay) runs and can be
exercised offline via tools/replay_canned_events.py, but real gameplay won't produce any
normalized events yet.
"""

from companion.protocol.events import NormalizedEvent


def parse_frame(raw: dict) -> list[NormalizedEvent]:
    # TODO(post Step-0 spike): dispatch on whatever discriminator field the live capture
    # reveals to one of: _parse_player_state, _parse_combat_tick, _parse_animation,
    # _parse_zone_change. Unrecognized shapes should keep returning [] rather than raising --
    # never let one unexpected frame shape take down the capture pipeline.
    return []
