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

HI_DEV_DIR_ACTION = {
    "left": "बाएँ मुड़ें",
    "right": "दाएँ मुड़ें",
    "slight left": "थोड़ा बाएँ रहें",
    "slight right": "थोड़ा दाएँ रहें",
    "sharp left": "तेज़ बाएँ मुड़ें",
    "sharp right": "तेज़ दाएँ मुड़ें",
    "straight": "सीधे चलते रहें",
    "uturn": "यू-टर्न लें",
}

HI_DEV_NOW_ACTION = {
    "left": "अभी बाएँ मुड़ें।",
    "right": "अभी दाएँ मुड़ें।",
    "slight left": "अभी थोड़ा बाएँ रहें।",
    "slight right": "अभी थोड़ा दाएँ रहें।",
    "sharp left": "अभी तेज़ बाएँ मुड़ें।",
    "sharp right": "अभी तेज़ दाएँ मुड़ें।",
    "straight": "अभी सीधे चलें।",
    "uturn": "अभी यू-टर्न लें।",
}

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
    near_m: float = 50.0
    now_m: float = 15.0
    skip_straight_steps: bool = True
    enable_kannada_driver: bool = True
    # Compatibility fields
    far_min_m: float = 400.0
    far_speed_factor: float = 40.0
    near_min_m: float = 50.0
    near_speed_factor: float = 12.0
    now_dist_m: float = 15.0
    moving_speed_threshold_mps: float = 8.0 / 3.6
    stop_speed_threshold_mps: float = 3.0 / 3.6
    enable_start_announcement: bool = True
    single_turn_announcement: bool = True


@dataclass
class AnnouncementState:
    step: int | None = None
    stage: str = "none"
    last_announced_stage: str = "ahead"
    announcement_id: int = 0
    off_route_announced: bool = False
    arrived_announced: bool = False
    announced_stages: dict[int, str] = field(default_factory=dict)
    last_announcement: Announcement | None = None
    last_announcement_step: Step | None = None

    @property
    def current_step(self) -> int | None:
        return self.step

    @current_step.setter
    def current_step(self, val: int | None) -> None:
        self.step = val

    def next_id(self) -> int:
        self.announcement_id += 1
        return self.announcement_id

    def reset(self) -> None:
        self.step = None
        self.stage = "none"
        self.last_announced_stage = "ahead"
        self.off_route_announced = False
        self.arrived_announced = False
        self.announced_stages.clear()
        self.last_announcement = None
        self.last_announcement_step = None


def decide(st: AnnouncementState, i: int, dist: float, cfg: AnnouncerConfig, mode: str = "walk") -> list[str]:
    events = []
    if i != st.step:                                  # previous maneuver passed, or first tick
        if st.stage in ("ahead", "near"):
            events.append("chime")                    # never miss the 'turn happened' sound
        st.step, st.stage = i, "none"
    if st.stage == "none":
        if dist > cfg.near_m * 1.5:
            events.append("ahead"); st.stage = "ahead"
        else:
            events.append("near"); st.stage = "near"
    if st.stage == "ahead" and dist <= cfg.near_m:
        events.append("near"); st.stage = "near"
    if st.stage == "near" and dist <= cfg.now_m:
        events.append("chime"); st.stage = "now"
    return events


def round_spoken_distance(dist_m: float) -> tuple[float, str]:
    """Distance rounding helper: <200 m nearest 10 m, 200-999 m nearest 50 m, >=1 km nearest 0.1 km."""
    if dist_m < 0:
        dist_m = 0.0
    if dist_m < 200.0:
        val = float(int((dist_m + 5.0) // 10.0) * 10)
        if dist_m > 0 and val == 0:
            val = 10.0
        return val, "m"
    if dist_m < 1000.0:
        val = float(int((dist_m + 25.0) // 50.0) * 50)
        if val >= 1000.0:
            return 1.0, "km"
        return val, "m"
    km = round(dist_m / 1000.0, 1)
    return max(1.0, km), "km"


def format_spoken_dist(val: float, unit: str, lang: str) -> str:
    """Format rounded distance for natural voice output and TTS caching."""
    if unit == "m":
        n = int(val)
        if lang == "kn":
            return f"{n} ಮೀಟರ್"
        if lang == "hi":
            return f"{n} मीटर"
        if lang == "hinglish":
            return f"{n} meter"
        return f"{n} meters" if n != 1 else "1 meter"

    km_str = f"{val:g}"
    if lang == "kn":
        return f"{km_str} ಕಿಲೋಮೀಟರ್"
    if lang == "hi":
        return f"{km_str} किलोमीटर"
    if lang == "hinglish":
        return f"{km_str} kilometer"
    return f"{km_str} kilometer" if val == 1.0 else f"{km_str} kilometers"


def _clean_sentence(text: str, max_words: int = 12) -> str:
    """Enforces at most max_words and single sentence formatting."""
    clean = " ".join(text.strip().split())
    if not clean.endswith((".", "।", "!")):
        clean += "."
    words = clean.split()
    if len(words) <= max_words:
        return clean
    truncated = " ".join(words[:max_words])
    return truncated.rstrip(",. ") + "."


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


def render_guidance(step: Step, dist_m: float, stage: str, lang: str, landmark: str | None = None) -> str:
    """ONE unified renderer used for speech, live text, and chat responses.

    Distance rounded to buckets: <200 m nearest 10 m, 200-999 m nearest 50 m, >=1 km nearest 0.1 km.
    Landmarks included only at stage == 'ahead'.
    """
    val, unit = round_spoken_distance(dist_m)
    dist_str = format_spoken_dist(val, unit, lang)
    valid_landmark = landmark.strip() if (stage == "ahead" and landmark and landmark.strip()) else None

    # Arrival
    if step.maneuver == "arrive":
        if stage in ("arrival", "now") or dist_m <= 5:
            if lang == "kn":
                return "ನೀವು ನಿಮ್ಮ ಗಮ್ಯಸ್ಥಾನವನ್ನು ತಲುಪಿದ್ದೀರಿ."
            if lang == "hi":
                return "आप अपनी मंज़िल पर पहुँच गए हैं।"
            if lang == "hinglish":
                return "Aap apni manzil par pahunch gaye hain."
            return "You have arrived at your destination."
        else:
            if lang == "kn":
                return f"{dist_str} ನಂತರ ಗಮ್ಯಸ್ಥಾನ ತಲುಪುತ್ತೀರಿ."
            if lang == "hi":
                return f"{dist_str} के बाद मंज़िल पर पहुँच जाएँगे।"
            if lang == "hinglish":
                return f"{dist_str} ke baad manzil par pahunch jaenge."
            return f"In {dist_str}, you will arrive."

    # Departure
    if step.maneuver == "depart":
        if stage == "now":
            if lang == "kn":
                return "ಈಗ ನೇರವಾಗಿ ಹೋಗಿ."
            if lang == "hi":
                return "अभी चलना शुरू करें।"
            if lang == "hinglish":
                return "Abhi chalna shuru karein."
            return "Start walking now."
        valid_road = step.road if (step.road and len(step.road.split()) <= 3) else None
        if lang == "kn":
            if valid_road:
                return f"{valid_road} ನಲ್ಲಿ ಪ್ರಯಾಣ ಪ್ರಾರಂಭಿಸಿ. {dist_str} ನೇರವಾಗಿ ಮುಂದುವರಿಯಿರಿ."
            return f"ಪ್ರಯಾಣ ಪ್ರಾರಂಭಿಸಿ, {dist_str} ನೇರವಾಗಿ ಮುಂದುವರಿಯಿರಿ."
        if lang == "hi":
            if valid_road:
                return f"{valid_road} पर चलना शुरू करें। {dist_str} आगे चलें।"
            return f"चलना शुरू करें। {dist_str} आगे चलें।"
        if lang == "hinglish":
            if valid_road:
                return f"{valid_road} par chalna shuru karein. {dist_str} aage chalein."
            return f"Chalna shuru karein. {dist_str} aage chalein."
        if valid_road:
            return f"Start walking on {valid_road}. Continue for {dist_str}."
        return f"Start walking. Continue for {dist_str}."

    # Turn / Maneuver Phrasing
    if stage == "now":
        if lang == "kn":
            if step.maneuver in ROUNDABOUT_MANEUVERS:
                phrase = "ಈಗ ರೌಂಡ್‌ಅಬೌಟ್ ತೆಗೆದುಕೊಳ್ಳಿ."
            elif step.maneuver == "fork":
                side = (step.modifier or "").replace("slight ", "")
                if side == "left":
                    phrase = "ಈಗ ಎಡ ಬದಿಯಲ್ಲಿ ಇರಿ."
                elif side == "right":
                    phrase = "ಈಗ ಬಲ ಬದಿಯಲ್ಲಿ ಇರಿ."
                else:
                    phrase = "ಈಗ ನೇರವಾಗಿ ಹೋಗಿ."
            elif step.maneuver == "depart":
                phrase = "ಈಗ ನೇರವಾಗಿ ಹೋಗಿ."
            else:
                mod = step.modifier or "straight"
                phrase = KN_NOW_ACTION.get(mod, "ಈಗ ನೇರವಾಗಿ ಹೋಗಿ.")
        elif lang == "hi":
            if step.maneuver in ROUNDABOUT_MANEUVERS:
                phrase = "अभी राउंडअबाउट लें।"
            else:
                mod = step.modifier or "straight"
                phrase = HI_DEV_NOW_ACTION.get(mod, "अभी सीधे चलें।")
        elif lang == "hinglish":
            if step.maneuver in ROUNDABOUT_MANEUVERS:
                phrase = "Abhi roundabout lein."
            else:
                mod = step.modifier or "straight"
                phrase = HI_NOW_ACTION.get(mod, "Abhi seedha chalein.")
        else:
            phrase = _now_phrase_en(step)
        return _clean_sentence(phrase, 12)

    # AHEAD or NEAR stage
    if lang == "kn":
        from app.services.places.aliases import get_kannada_name
        if step.maneuver in ROUNDABOUT_MANEUVERS:
            action = "ರೌಂಡ್‌ಅಬೌಟ್ ತೆಗೆದುಕೊಳ್ಳಿ"
        elif step.maneuver == "fork":
            side = (step.modifier or "").replace("slight ", "")
            if side == "left":
                action = "ಎಡ ಬದಿಯಲ್ಲಿ ಇರಿ"
            elif side == "right":
                action = "ಬಲ ಬದಿಯಲ್ಲಿ ಇರಿ"
            else:
                action = "ನೇರವಾಗಿ ಮುಂದುವರಿಯಿರಿ"
        else:
            action = KN_DIR_ACTION.get(step.modifier or "straight", "ನೇರವಾಗಿ ಮುಂದುವರಿಯಿರಿ")

        if valid_landmark:
            lm_kn = get_kannada_name(valid_landmark) or valid_landmark
            phrase = f"{dist_str} ನಂತರ {lm_kn} ಹತ್ತಿರ {action}."
        else:
            phrase = f"{dist_str} ನಂತರ {action}."

    elif lang == "hi":
        if step.maneuver in ROUNDABOUT_MANEUVERS:
            action = "राउंडअबाउट लें"
        elif step.maneuver == "fork":
            side = (step.modifier or "").replace("slight ", "")
            action = "बाएँ रहें" if side == "left" else ("दाएँ रहें" if side == "right" else "सीधे चलते रहें")
        else:
            action = HI_DEV_DIR_ACTION.get(step.modifier or "straight", "सीधे चलते रहें")

        if valid_landmark:
            phrase = f"{dist_str} के बाद {valid_landmark} के पास {action}।"
        else:
            phrase = f"{dist_str} के बाद {action}।"

    elif lang == "hinglish":
        if step.maneuver in ROUNDABOUT_MANEUVERS:
            action = "roundabout lena"
        elif step.maneuver == "fork":
            side = (step.modifier or "").replace("slight ", "")
            action = f"{side} rehna" if side in ("left", "right") else "seedha chalte rehna"
        else:
            action = HI_DIR_ACTION.get(step.modifier or "straight", "seedha chalte rehna")

        if valid_landmark:
            phrase = f"{dist_str} ke baad {valid_landmark} ke paas {action}."
        else:
            phrase = f"{dist_str} ke baad {action}."

    else:  # English
        action = _action_phrase_en(step)
        if valid_landmark:
            phrase = f"In {dist_str}, {action} near {valid_landmark}."
        else:
            phrase = f"In {dist_str}, {action}."

    return _clean_sentence(phrase, 12)


def build_arrival_announcement(lang: str, config: AnnouncerConfig = AnnouncerConfig()) -> Announcement:
    if lang == "kn" and config.enable_kannada_driver:
        text = "ನೀವು ನಿಮ್ಮ ಗಮ್ಯಸ್ಥಾನವನ್ನು ತಲುಪಿದ್ದೀರಿ."
    elif lang == "hi":
        text = "आप अपनी मंज़िल पर पहुँच गए हैं।"
    elif lang == "hinglish":
        text = "Aap apni manzil par pahunch gaye hain."
    else:
        text = "You have arrived at your destination."
    return Announcement(
        id=0,
        text=_clean_sentence(text, 12),
        stage="arrival",
        lang=lang,
        speak=True,
        chime=False,
        priority="high",
        language=lang,
    )


def build_reroute_announcement(lang: str, config: AnnouncerConfig = AnnouncerConfig()) -> Announcement:
    if lang == "kn" and config.enable_kannada_driver:
        text = "ದಾರಿಯಿಂದ ಹೊರಗಿದ್ದೀರಿ, ಹೊಸ ದಾರಿ ಹುಡುಕುತ್ತಿದ್ದೇವೆ."
    elif lang == "hi":
        text = "रास्ते से हट गए हैं, नया रास्ता ढूँढ रहे हैं।"
    elif lang == "hinglish":
        text = "Route se hat gaye, naya rasta dhoond rahe hain."
    else:
        text = "Off route, finding a new route."
    return Announcement(
        id=0,
        text=_clean_sentence(text, 12),
        stage="reroute",
        lang=lang,
        speak=True,
        chime=False,
        priority="high",
        language=lang,
    )


def build_driver_instruction(
    *,
    stage: str,
    step: Step,
    distance_to_next_m: float,
    landmark_name: str | None = None,
    lang: str = "en",
    config: AnnouncerConfig = AnnouncerConfig(),
) -> str:
    """Wrapper calling render_guidance for backwards compatibility."""
    stage_for_render = "ahead" if (stage in ("far", "near") and landmark_name) else stage
    return render_guidance(step, distance_to_next_m, stage_for_render, lang, landmark_name)


def check_announcement(
    *,
    distance_to_next_m: float | None,
    speed_mps: float = 0.0,
    step_index: int | None,
    step: Step | None,
    on_route: bool,
    arrived: bool,
    state: AnnouncementState,
    landmark_name: str | None = None,
    lang: str = "en",
    config: AnnouncerConfig = AnnouncerConfig(),
    prev_step_distance_m: float = 0.0,
    mode: str = "walk",
) -> Announcement | None:
    """Pure decision function for spoken announcements and chimes.

    Emits {id, stage, text, lang, speak: bool, chime: bool}.
    Chime event at NOW stage has speak=False, chime=True.
    """
    if arrived:
        if not state.arrived_announced:
            state.arrived_announced = True
            ann = build_arrival_announcement(lang, config)
            ann.id = state.next_id()
            state.last_announcement = ann
            return ann
        return None

    if not on_route:
        if not state.off_route_announced:
            state.off_route_announced = True
            ann = build_reroute_announcement(lang, config)
            ann.id = state.next_id()
            state.last_announcement = ann
            return ann
        return None

    state.off_route_announced = False

    if step_index is None or step is None or distance_to_next_m is None:
        return None

    # Mode-tailored thresholds
    if mode == "drive":
        near_m = max(120.0, speed_mps * 12.0)
        now_m = 30.0
    else:
        near_m = 50.0
        now_m = 15.0

    # If config specifically provided non-default near_m/now_m, respect it
    if config.near_m != 50.0 or config.now_m != 15.0:
        near_m = config.near_m
        now_m = config.now_m

    cfg = AnnouncerConfig(
        near_m=near_m,
        now_m=now_m,
        skip_straight_steps=config.skip_straight_steps,
        enable_kannada_driver=config.enable_kannada_driver,
    )

    # Skip straight / continue steps
    is_straight = (step.modifier == "straight" or step.maneuver == "continue") and step.maneuver not in ("depart", "arrive")
    if cfg.skip_straight_steps and is_straight:
        events = []
        if step_index != state.step:
            if state.stage in ("ahead", "near"):
                events.append("chime")
            state.step = step_index
            state.stage = "skipped"
        if "chime" in events:
            ann = Announcement(
                id=state.next_id(),
                stage="chime",
                text="",
                lang=lang,
                speak=False,
                chime=True,
                priority="normal",
                language=lang,
            )
            state.last_announcement = ann
            return ann
        return None

    events = decide(state, step_index, distance_to_next_m, cfg, mode)
    if not events:
        return None

    has_chime = "chime" in events
    has_ahead = "ahead" in events
    has_near = "near" in events

    if has_ahead or has_near:
        target_stage = "ahead" if has_ahead else "near"
        state.last_announced_stage = target_stage
        text = render_guidance(step, distance_to_next_m, target_stage, lang, landmark_name)
        ann = Announcement(
            id=state.next_id(),
            stage=target_stage,
            text=text,
            lang=lang,
            speak=True,
            chime=has_chime,
            priority="normal",
            language=lang,
        )
        state.announced_stages[step_index] = target_stage
        state.last_announcement = ann
        state.last_announcement_step = step
        return ann

    elif has_chime:
        ann = Announcement(
            id=state.next_id(),
            stage="chime",
            text="",
            lang=lang,
            speak=False,
            chime=True,
            priority="normal",
            language=lang,
        )
        state.announced_stages[step_index] = "now"
        state.last_announcement = ann
        return ann

    return None
