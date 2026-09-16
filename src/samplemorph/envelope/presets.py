from __future__ import annotations

from typing import Final

from samplemorph.envelope.settings import EnvelopeSettings

KEEPS_FIRST: Final[EnvelopeSettings] = EnvelopeSettings(switch_weight=1.0)
KEEPS_SECOND: Final[EnvelopeSettings] = EnvelopeSettings(switch_weight=0.0)
SWITCHES_HALFWAY: Final[EnvelopeSettings] = EnvelopeSettings(switch_weight=0.5)

ENVELOPE_PRESETS: Final[dict[str, EnvelopeSettings]] = {
    "first": KEEPS_FIRST,
    "second": KEEPS_SECOND,
    "halfway": SWITCHES_HALFWAY,
}
DEFAULT_ENVELOPE_PRESET_NAME: Final[str] = "first"
