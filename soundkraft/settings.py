"""Sensory/accessibility settings for a user, and their allowed ranges."""

from __future__ import annotations

DEFAULTS: dict = {
    "text_scale": 1.25,         # UI font multiplier
    "target_scale": 1.0,        # touch-target size multiplier
    "contrast": "standard",     # "standard" | "high"
    "audio_cues": True,         # feedback tones
    "spoken_instructions": True,  # text-to-speech instructions
    "input_mode": "swipe",      # "swipe" | "tap" (binary-choice games)
    "pace": 1.0,                # multiplies every time window
}

TEXT_SCALES = [1.0, 1.25, 1.5, 1.75, 2.0]
TARGET_SCALE_RANGE = (1.0, 1.6)
PACE_RANGE = (1.0, 2.0)


def normalise(raw: dict | None) -> dict:
    """Merge `raw` over the defaults and clamp every value into its allowed range."""
    s = dict(DEFAULTS)
    for key, value in (raw or {}).items():
        if key in DEFAULTS and value is not None:
            s[key] = value
    s["text_scale"] = min(TEXT_SCALES, key=lambda v: abs(v - float(s["text_scale"])))
    s["target_scale"] = round(min(max(float(s["target_scale"]), TARGET_SCALE_RANGE[0]), TARGET_SCALE_RANGE[1]), 2)
    s["pace"] = round(min(max(float(s["pace"]), PACE_RANGE[0]), PACE_RANGE[1]), 2)
    s["contrast"] = "high" if s["contrast"] == "high" else "standard"
    s["input_mode"] = "tap" if s["input_mode"] == "tap" else "swipe"
    s["audio_cues"] = _as_bool(s["audio_cues"])
    s["spoken_instructions"] = _as_bool(s["spoken_instructions"])
    return s


def _as_bool(v) -> bool:
    if isinstance(v, str):
        return v.lower() in {"1", "true", "yes", "on"}
    return bool(v)
