"""Driver Mode Proactive Guidance Announcer.
Pure functions for deterministic, voice-first spoken navigation in Bangalore.

Regulatory Context:
Regulation 37 of Motor Vehicles (Driving) Regulations 2020 allows phone usage
for route navigation only when fixed on the dashboard. This module provides
hands-free, voice-first proactive guidance designed so the driver never needs
to look at or touch the phone while driving.
(Disclaimer: For regulatory awareness only; not legal advice).
"""

from dataclasses import dataclass, field
from typing import Literal

from app.schemas.nav_state import Announcement
from app.schemas.route import Step

# Order of proactive guidance stages
STAGE_RANKS: dict[str, int] = {
    "far": 1,
    "near": 2,
    "now": 3,
}

# Rounded distance buckets in meters (< 900m)
METER_BUCKETS: list[int] = [50, 100, 150, 200, 300, 400, 500, 600, 800]

ROUNDABOUT_MANEUVERS = ("roundabout", "rotary", "roundabout turn", "exit roundabout", "exit rotary")

HI_DIR_ACTION = {
    "left": "left lena",
    "right": "right lena",
    "slight left": "thoda left rehna",
    "slight right": "thoda right rehna",
    "sharp left": "tez left lena",
    "sharp right": "tez right lena",
    "straight": "seedha chalte rehna",
    "uturn": "U-turn lena",
}

HI_NOW_ACTION = {
    "left": "Abhi left lein.",
    "right": "Abhi right lein.",
    "slight left": "Abhi thoda left lein.",
    "slight right": "Abhi thoda right lein.",
    "sharp left": "Abhi tez left lein.",
    "sharp right": "Abhi tez right lein.",
    "straight": "Abhi seedha chalein.",
    "uturn": "Abhi U-turn lein.",
}

# UNVERIFIED: Kannada driver templates need review by a native speaker before enabling.
KN_DIR_ACTION = {
    "left": "ಎಡಕ್ಕೆ ತಿರುಗಿ",
    "right": "ಬಲಕ್ಕೆ ತಿರುಗಿ",
    "slight left": "ಸ್ವಲ್ಪ ಎಡಕ್ಕೆ ಇರಿ",
    "slight right": "ಸ್ವಲ್ಪ ಬಲಕ್ಕೆ ಇರಿ",
    "sharp left": "ಪೂರ್ತಿ ಎಡಕ್ಕೆ ತಿರುಗಿ",
    "sharp right": "ಪೂರ್ತಿ ಬಲಕ್ಕೆ ತಿರುಗಿ",
    "straight": "ನೇರವಾಗಿ ಮುಂದುವರಿಯಿರಿ",
    "uturn": "ಯು-ಟರ್ನ್ ತೆಗೆದುಕೊಳ್ಳಿ",
}

KN_NOW_ACTION = {
    "left": "ಈಗ ಎಡಕ್ಕೆ ತಿರುಗಿ.",
    "right": "ಈಗ ಬಲಕ್ಕೆ ತಿರುಗಿ.",
    "slight left": "ಈಗ ಸ್ವಲ್ಪ ಎಡಕ್ಕೆ ಇರಿ.",
    "slight right": "ಈಗ ಸ್ವಲ್ಪ ಬಲಕ್ಕೆ ಇರಿ.",
    "sharp left": "ಈಗ ಪೂರ್ತಿ ಎಡಕ್ಕೆ ತಿರುಗಿ.",
    "sharp right": "ಈಗ ಪೂರ್ತಿ ಬಲಕ್ಕೆ ತಿರುಗಿ.",
    "straight": "ಈಗ ನೇರವಾಗಿ ಹೋಗಿ.",
    "uturn": "ಈಗ ಯು-ಟರ್ನ್ ತೆಗೆದುಕೊಳ್ಳಿ.",
}


@dataclass(frozen=True)
class AnnouncerConfig:
    far_min_m: float = 400.0
    far_speed_factor: float = 40.0
    near_min_m: float = 120.0
    near_speed_factor: float = 15.0
    now_dist_m: float = 30.0
    moving_speed_threshold_mps: float = 8.0 / 3.6  # 8 km/h in m/s (~2.22 m/s)
    stop_speed_threshold_mps: float = 3.0 / 3.6    # 3 km/h in m/s (~0.83 m/s)
    enable_kannada_driver: bool = False            # Flagged UNVERIFIED until reviewed


@dataclass
class AnnouncementState:
    announced_stages: dict[int, str] = field(default_factory=dict)
    off_route_announced: bool = False
    arrived_announced: bool = False
    last_announcement: Announcement | None = None

    def reset(self) -> None:
        self.announced_stages.clear()
        self.off_route_announced = False
        self.arrived_announced = False
        self.last_announcement = None


def round_spoken_distance(dist_m: float) -> tuple[float, str]:
    """Rounds distance to {50,100,150,200,300,400,500,600,800}m or whole/half km.
    Returns (value, unit) where unit is 'm' or 'km'.
    """
    if dist_m < 900.0:
        chosen = min(METER_BUCKETS, key=lambda b: abs(b - dist_m))
        return float(chosen), "m"
    km = round((dist_m / 1000.0) * 2.0) / 2.0
    km = max(1.0, km)
    return km, "km"


def format_spoken_dist(val: float, unit: str, lang: str) -> str:
    """Format rounded distance for natural voice output and TTS caching."""
    if unit == "m":
        n = int(val)
        if lang == "kn":
            return f"{n} ಮೀಟರ್"
        if lang == "hinglish":
            return f"{n} meter"
        return f"{n} meters"
    km_str = f"{val:g}"
    if lang == "kn":
        return f"{km_str} ಕಿಲೋಮೀಟರ್"
    if lang == "hinglish":
        return f"{km_str} kilometer"
    return f"{km_str} kilometer" if val == 1.0 else f"{km_str} kilometers"


def _clean_sentence(text: str, max_words: int = 12) -> str:
    """Enforces at most max_words and single sentence formatting."""
    clean = " ".join(text.strip().split())
    if not clean.endswith("."):
        clean += "."
    words = clean.split()
    if len(words) <= max_words:
        return clean
    # Fallback truncate cleanly
    truncated = " ".join(words[:max_words])
    return truncated.rstrip(",. ") + "."


def build_arrival_announcement(lang: str, config: AnnouncerConfig) -> Announcement:
    if lang == "kn" and config.enable_kannada_driver:
        text = "ನೀವು ನಿಮ್ಮ ಗಮ್ಯಸ್ಥಾನವನ್ನು ತಲುಪಿದ್ದೀರಿ."
    elif lang == "hinglish":
        text = "Aap apni manzil par pahunch gaye hain."
    else:
        text = "You have arrived at your destination."
    return Announcement(
        text=_clean_sentence(text, 12),
        stage="arrival",
        priority="high",
        language=lang,
    )


def build_reroute_announcement(lang: str, config: AnnouncerConfig) -> Announcement:
    if lang == "kn" and config.enable_kannada_driver:
        text = "ದಾರಿಯಿಂದ ಹೊರಗಿದ್ದೀರಿ, ಹೊಸ ದಾರಿ ಹುಡುಕುತ್ತಿದ್ದೇವೆ."
    elif lang == "hinglish":
        text = "Route se hat gaye, naya rasta dhoond rahe hain."
    else:
        text = "Off route, finding a new route."
    return Announcement(
        text=_clean_sentence(text, 12),
        stage="reroute",
        priority="high",
        language=lang,
    )


def _action_phrase_en(step: Step) -> str:
    if step.maneuver in ROUNDABOUT_MANEUVERS:
        return "take the roundabout"
    if step.modifier == "uturn":
        return "make a U-turn"
    if step.maneuver == "fork":
        side = (step.modifier or "").replace("slight ", "")
        return f"keep {side}" if side in ("left", "right") else "continue"
    mod = step.modifier
    if mod == "slight left":
        return "keep slightly left"
    if mod == "slight right":
        return "keep slightly right"
    if mod == "sharp left":
        return "turn sharply left"
    if mod == "sharp right":
        return "turn sharply right"
    if mod in ("left", "right"):
        return f"turn {mod}"
    return "continue straight"


def _now_phrase_en(step: Step) -> str:
    if step.maneuver in ROUNDABOUT_MANEUVERS:
        return "Take the roundabout now."
    if step.modifier == "uturn":
        return "Make a U-turn now."
    if step.maneuver == "fork":
        side = (step.modifier or "").replace("slight ", "")
        return f"Keep {side} now." if side in ("left", "right") else "Continue now."
    mod = step.modifier
    if mod == "slight left":
        return "Keep slightly left now."
    if mod == "slight right":
        return "Keep slightly right now."
    if mod == "sharp left":
        return "Turn sharply left now."
    if mod == "sharp right":
        return "Turn sharply right now."
    if mod in ("left", "right"):
        return f"Turn {mod} now."
    return "Continue straight now."


def _build_driver_phrase_en(
    stage: str,
    step: Step,
    dist_str: str,
    landmark: str | None,
    road: str | None,
) -> str:
    if stage == "now":
        return _now_phrase_en(step)

    if step.maneuver == "arrive":
        return f"In {dist_str}, you will arrive."

    action = _action_phrase_en(step)

    # Road name only if 3 words or fewer
    valid_road = road if road and len(road.split()) <= 3 and "roundabout" not in action else None

    # Landmark only at 'near' stage and only if verified
    valid_landmark = landmark if stage == "near" and landmark and len(landmark.strip()) > 0 else None

    if valid_landmark:
        candidate = f"In {dist_str}, {action} near {valid_landmark}."
        if len(candidate.split()) <= 12:
            return candidate

    if valid_road:
        candidate = f"In {dist_str}, {action} onto {valid_road}."
        if len(candidate.split()) <= 12:
            return candidate

    return f"In {dist_str}, {action}."


def _build_driver_phrase_hi(
    stage: str,
    step: Step,
    dist_str: str,
    landmark: str | None,
    road: str | None,
) -> str:
    if stage == "now":
        if step.maneuver in ROUNDABOUT_MANEUVERS:
            return "Abhi roundabout lein."
        mod = step.modifier or "straight"
        return HI_NOW_ACTION.get(mod, "Abhi seedha chalein.")

    if step.maneuver == "arrive":
        return f"{dist_str} ke baad manzil par pahunch jaenge."

    if step.maneuver in ROUNDABOUT_MANEUVERS:
        action = "roundabout lena"
    else:
        mod = step.modifier or "straight"
        action = HI_DIR_ACTION.get(mod, "seedha chalte rehna")

    valid_road = road if road and len(road.split()) <= 3 and "roundabout" not in action else None
    valid_landmark = landmark if stage == "near" and landmark and len(landmark.strip()) > 0 else None

    if valid_landmark:
        candidate = f"{dist_str} ke baad {valid_landmark} ke paas {action}."
        if len(candidate.split()) <= 12:
            return candidate

    if valid_road:
        candidate = f"{dist_str} ke baad {valid_road} par {action}."
        if len(candidate.split()) <= 12:
            return candidate

    return f"{dist_str} ke baad {action}."


def _build_driver_phrase_kn(
    stage: str,
    step: Step,
    dist_str: str,
    landmark: str | None,
    road: str | None,
) -> str:
    # UNVERIFIED: Kannada driver templates need review by a native speaker before enabling.
    if stage == "now":
        if step.maneuver in ROUNDABOUT_MANEUVERS:
            return "ಈಗ ರೌಂಡ್‌ಅಬೌಟ್ ತೆಗೆದುಕೊಳ್ಳಿ."
        mod = step.modifier or "straight"
        return KN_NOW_ACTION.get(mod, "ಈಗ ನೇರವಾಗಿ ಹೋಗಿ.")

    if step.maneuver == "arrive":
        return f"{dist_str} ನಂತರ ಗಮ್ಯಸ್ಥಾನ ತಲುಪುತ್ತೀರಿ."

    if step.maneuver in ROUNDABOUT_MANEUVERS:
        action = "ರೌಂಡ್‌ಅಬೌಟ್ ತೆಗೆದುಕೊಳ್ಳಿ"
    else:
        mod = step.modifier or "straight"
        action = KN_DIR_ACTION.get(mod, "ನೇರವಾಗಿ ಮುಂದುವರಿಯಿರಿ")

    valid_road = road if road and len(road.split()) <= 3 and "ರೌಂಡ್‌ಅಬೌಟ್" not in action else None
    valid_landmark = landmark if stage == "near" and landmark and len(landmark.strip()) > 0 else None

    if valid_landmark:
        candidate = f"{dist_str} ನಂತರ {valid_landmark} ಹತ್ತಿರ {action}."
        if len(candidate.split()) <= 12:
            return candidate

    if valid_road:
        candidate = f"{dist_str} ನಂತರ {valid_road} ನಲ್ಲಿ {action}."
        if len(candidate.split()) <= 12:
            return candidate

    return f"{dist_str} ನಂತರ {action}."


def build_driver_instruction(
    *,
    stage: str,
    step: Step,
    distance_to_next_m: float,
    landmark_name: str | None = None,
    lang: str = "en",
    config: AnnouncerConfig = AnnouncerConfig(),
) -> str:
    """Generates concise driver phrasing (<= 12 words, 1 sentence)."""
    val, unit = round_spoken_distance(distance_to_next_m)
    dist_str = format_spoken_dist(val, unit, lang)

    if lang == "kn" and config.enable_kannada_driver:
        phrase = _build_driver_phrase_kn(stage, step, dist_str, landmark_name, step.road)
    elif lang == "hinglish":
        phrase = _build_driver_phrase_hi(stage, step, dist_str, landmark_name, step.road)
    else:
        phrase = _build_driver_phrase_en(stage, step, dist_str, landmark_name, step.road)

    return _clean_sentence(phrase, max_words=12)


def check_announcement(
    *,
    distance_to_next_m: float | None,
    speed_mps: float,
    step_index: int | None,
    step: Step | None,
    on_route: bool,
    arrived: bool,
    state: AnnouncementState,
    landmark_name: str | None = None,
    lang: str = "en",
    config: AnnouncerConfig = AnnouncerConfig(),
) -> Announcement | None:
    """Pure decision function for spoken announcements.

    Evaluates:
    - Arrival (at most once)
    - Off-route excursion (at most once per excursion)
    - Maneuver stages: "far", "near", "now" (each announced at most once)
    - Skips earlier stages if first sighting occurs within a nearer threshold
    - Never repeats an already announced stage for the same maneuver
    """
    if arrived:
        if not state.arrived_announced:
            state.arrived_announced = True
            ann = build_arrival_announcement(lang, config)
            state.last_announcement = ann
            return ann
        return None

    if not on_route:
        if not state.off_route_announced:
            state.off_route_announced = True
            ann = build_reroute_announcement(lang, config)
            state.last_announcement = ann
            return ann
        return None

    # Reset off-route flag once back on route so future deviations trigger a warning
    state.off_route_announced = False

    if step_index is None or step is None or distance_to_next_m is None:
        return None

    # Threshold calculations
    far_thresh = max(config.far_min_m, speed_mps * config.far_speed_factor)
    near_thresh = max(config.near_min_m, speed_mps * config.near_speed_factor)
    now_thresh = config.now_dist_m

    if distance_to_next_m <= now_thresh:
        eligible_stage = "now"
    elif distance_to_next_m <= near_thresh:
        eligible_stage = "near"
    elif distance_to_next_m <= far_thresh:
        eligible_stage = "far"
    else:
        return None

    prev_stage = state.announced_stages.get(step_index)
    prev_rank = STAGE_RANKS.get(prev_stage, 0) if prev_stage else 0
    eligible_rank = STAGE_RANKS[eligible_stage]

    # Only announce if this stage is higher (nearer) than any already announced stage
    if eligible_rank <= prev_rank:
        return None

    state.announced_stages[step_index] = eligible_stage
    priority: Literal["normal", "high"] = "high" if eligible_stage == "now" else "normal"

    text = build_driver_instruction(
        stage=eligible_stage,
        step=step,
        distance_to_next_m=distance_to_next_m,
        landmark_name=landmark_name,
        lang=lang,
        config=config,
    )

    ann = Announcement(
        text=text,
        stage=eligible_stage,  # type: ignore[arg-type]
        priority=priority,
        language=lang,
    )
    state.last_announcement = ann
    return ann
