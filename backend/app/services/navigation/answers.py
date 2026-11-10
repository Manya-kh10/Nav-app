import time

from app.schemas.chat import ChatResponse
from app.schemas.nav_state import NavStatus
from app.schemas.route import Step
from app.services.intent.classifier import _DEVANAGARI, _KANNADA, _LATIN, classify
from app.services.navigation.announcer import (
    AnnouncerConfig,
    build_driver_instruction,
    format_spoken_dist,
    round_spoken_distance,
)
from app.services.navigation.sessions import Session
from app.services.navigation.templates import fmt_dist, live_instruction
from app.services.traffic.incidents import filter_incidents_on_route
from app.services.traffic.provider import TrafficLevel

STALE_S = 30  # a position older than this is not used to answer
ROUNDABOUT = ("roundabout", "rotary", "roundabout turn", "exit roundabout", "exit rotary")
HI_DIR = {
    "left": "left", "right": "right", "slight left": "thoda left", "slight right": "thoda right",
    "sharp left": "tez left", "sharp right": "tez right", "straight": "seedha", "uturn": "U-turn",
}
HI_DEV_DIR = {
    "left": "बाएँ", "right": "दाएँ", "slight left": "थोड़ा बाएँ", "slight right": "थोड़ा दाएँ",
    "sharp left": "तेज़ बाएँ", "sharp right": "तेज़ दाएँ", "straight": "सीधे", "uturn": "यू-टर्न",
}
KN_DIR = {
    "left": "ಎಡಕ್ಕೆ", "right": "ಬಲಕ್ಕೆ", "slight left": "ಸ್ವಲ್ಪ ಎಡಕ್ಕೆ", "slight right": "ಸ್ವಲ್ಪ ಬಲಕ್ಕೆ",
    "sharp left": "ಪೂರ್ತಿ ಎಡಕ್ಕೆ", "sharp right": "ಪೂರ್ತಿ ಬಲಕ್ಕೆ", "straight": "ನೇರವಾಗಿ", "uturn": "ಯು-ಟರ್ನ್",
}


def fmt_dist_hi(m: float) -> str:
    if m < 100:
        val = max(0, int(round(m)))
        return f"{val} meter"
    r = int(round(m / 10.0)) * 10
    if r < 1000:
        return f"{r} meter"
    return f"{round(m / 1000, 1):g} kilometer"


def fmt_dist_hi_dev(m: float) -> str:
    if m < 100:
        val = max(0, int(round(m)))
        return f"{val} मीटर"
    r = int(round(m / 10.0)) * 10
    if r < 1000:
        return f"{r} मीटर"
    return f"{round(m / 1000, 1):g} किलोमीटर"


def fmt_dist_kn(m: float) -> str:
    if m < 100:
        val = max(0, int(round(m)))
        return f"{val} ಮೀಟರ್"
    r = int(round(m / 10.0)) * 10
    if r < 1000:
        return f"{r} ಮೀಟರ್"
    return f"{round(m / 1000, 1):g} ಕಿಲೋಮೀಟರ್"


def next_hinglish(step: Step, dist_m: float, landmark: str | None) -> str:
    d = fmt_dist_hi(dist_m)
    if step.maneuver == "arrive":
        if dist_m <= 5:
            return "Aap apni manzil par pahunch gaye hain."
        return f"{d} ke baad aap apni manzil par pahunch jaoge."
    mod = step.modifier
    if step.maneuver in ROUNDABOUT:
        action = "roundabout lena"
    elif mod == "uturn":
        action = "U-turn lena"
    elif step.maneuver == "fork":
        side = (mod or "").replace("slight ", "")
        action = f"{side} side rehna" if side in ("left", "right") else "seedha chalte rahiye"
    elif mod in HI_DIR and mod != "straight":
        action = f"{HI_DIR[mod]} mudna"
        if step.maneuver == "end of road":
            action = f"road ke end par {action}"
    else:
        action = "seedha chalte rahiye"
    road = f"{step.road} par " if step.road and "roundabout" not in action else ""
    if dist_m <= 5:
        text = f"Abhi {road}{action}"
    else:
        text = f"{d} ke baad {road}{action}"
    if landmark:
        text += f", {landmark} ke paas"
    return text + "."


def next_hindi_devanagari(step: Step, dist_m: float, landmark: str | None) -> str:
    d = fmt_dist_hi_dev(dist_m)
    if step.maneuver == "arrive":
        if dist_m <= 5:
            return "आप अपनी मंज़िल पर पहुँच गए हैं।"
        return f"{d} के बाद आप अपनी मंज़िल पर पहुँच जाएँगे।"
    mod = step.modifier
    if step.maneuver in ROUNDABOUT:
        action = "गोलचक्कर लें"
    elif mod == "uturn":
        action = "यू-टर्न लें"
    elif step.maneuver == "fork":
        side = (mod or "").replace("slight ", "")
        action = "बाएँ तरफ़ रहें" if side == "left" else ("दाएँ तरफ़ रहें" if side == "right" else "सीधे चलते रहिए")
    elif mod in HI_DEV_DIR and mod != "straight":
        action = f"{HI_DEV_DIR[mod]} मुड़ें"
        if step.maneuver == "end of road":
            action = f"सड़क के अंत पर {action}"
    else:
        action = "सीधे चलते रहिए"
    road = f"{step.road} पर " if step.road and "गोलचक्कर" not in action else ""
    if dist_m <= 5:
        text = f"अभी {road}{action}"
    else:
        text = f"{d} के बाद {road}{action}"
    if landmark:
        text += f", {landmark} के पास"
    return text + "।"


def next_kannada(step: Step, dist_m: float, landmark: str | None) -> str:
    from app.services.places.aliases import get_kannada_name
    d = fmt_dist_kn(dist_m)
    if step.maneuver == "arrive":
        if dist_m <= 5:
            return "ನೀವು ನಿಮ್ಮ ಗಮ್ಯಸ್ಥಾನವನ್ನು ತಲುಪಿದ್ದೀರಿ."
        return f"{d} ನಂತರ ನೀವು ನಿಮ್ಮ ಗಮ್ಯಸ್ಥಾನವನ್ನು ತಲುಪುತ್ತೀರಿ."
    mod = step.modifier
    if step.maneuver in ROUNDABOUT:
        action = "ರೌಂಡ್‌ಅಬೌಟ್ ತೆಗೆದುಕೊಳ್ಳಿ"
    elif mod == "uturn":
        action = "ಯು-ಟರ್ನ್ ತೆಗೆದುಕೊಳ್ಳಿ"
    elif step.maneuver == "fork":
        side = (mod or "").replace("slight ", "")
        action = f"{KN_DIR.get(side, '')} ಬದಿಯಲ್ಲಿ ಇರಿ" if side in ("left", "right") else "ನೇರವಾಗಿ ಮುಂದುವರಿಯಿರಿ"
    elif mod in KN_DIR and mod != "straight":
        action = f"{KN_DIR[mod]} ತಿರುಗಿ"
        if step.maneuver == "end of road":
            action = f"ರಸ್ತೆಯ ಕೊನೆಯಲ್ಲಿ {action}"
    else:
        action = "ನೇರವಾಗಿ ಮುಂದುವರಿಯಿರಿ"
    road = f"{step.road} ನಲ್ಲಿ " if step.road and "ರೌಂಡ್‌ಅಬೌಟ್" not in action else ""
    if dist_m <= 5:
        text = f"ಈಗ {road}{action}"
    else:
        text = f"{d} ನಂತರ {road}{action}"
    if landmark:
        lm_kn = get_kannada_name(landmark) or landmark
        text += f", {lm_kn} ಹತ್ತಿರ"
    return text + "."


def _fresh_status(s: Session) -> NavStatus | None:
    if s.last_status is not None:
        return s.last_status
    if s.route and s.route.steps:
        steps = s.route.steps
        nxt_idx = 0
        dist_next = steps[0].distance_m
        if steps[0].maneuver == "depart" and len(steps) > 1:
            nxt_idx = 1
            dist_next = steps[0].distance_m
        return NavStatus(
            on_route=True,
            needs_reroute=False,
            gps_quality="ok",
            distance_from_route_m=0.0,
            remaining_m=float(s.route.distance_m),
            remaining_s=float(s.route.duration_s),
            arrived=False,
            next_index=nxt_idx,
            next_text=steps[nxt_idx].road or None,
            distance_to_next_m=float(dist_next),
            speed_mps=0.0,
        )
    return None


def answer(s: Session, message: str, driver_mode: bool = False, user_lang: str | None = None) -> ChatResponse:
    intent, lang = classify(message)
    norm_user_lang = None
    if user_lang:
        ul = user_lang.lower()
        if "kn" in ul:
            norm_user_lang = "kn"
        elif ul in ("hi", "hi-in"):
            norm_user_lang = "hi"
        elif "hinglish" in ul:
            norm_user_lang = "hinglish"
        elif "en" in ul:
            norm_user_lang = "en"

    has_dev = bool(_DEVANAGARI.search(message))
    has_kn = bool(_KANNADA.search(message))
    has_lat = bool(_LATIN.search(message))

    if has_kn:
        reply_lang = "kn"
    elif has_dev and has_lat:
        reply_lang = norm_user_lang if norm_user_lang == "hi" else "hinglish"
    elif has_dev:
        reply_lang = "hi"
    elif norm_user_lang in ("kn", "hi", "hinglish"):
        reply_lang = norm_user_lang
    elif lang in ("kn", "hi", "hinglish"):
        reply_lang = lang
    elif s.driver_lang in ("kn", "hi", "hinglish") and intent != "unknown":
        reply_lang = s.driver_lang
    else:
        reply_lang = "en"

    def pick(en: str, hin: str, kn: str, hi_dev: str | None = None) -> str:
        if reply_lang == "kn":
            return kn
        if reply_lang == "hi":
            return hi_dev or hin
        if reply_lang == "hinglish":
            return hin
        return en

    def reply(text: str, has_loc: bool = True, remember: bool = False) -> ChatResponse:
        if remember:
            s.last_answer = (text, reply_lang)
        return ChatResponse(intent=intent, lang=reply_lang, text=text, has_location=has_loc)

    if intent == "start_navigation":
        return reply(pick(
            "Starting walk. Let's go!",
            "Chalna shuru kar rahe hain. Chalo!",
            "ನಡೆಯಲು ಪ್ರಾರಂಭಿಸುತ್ತಿದ್ದೇವೆ. ಹೋಗೋಣ!",
            hi_dev="चलना शुरू कर रहे हैं। चलिए!",
        ), has_loc=False)

    if intent == "unknown":
        if driver_mode:
            return reply(pick(
                "Ask next turn, route status, or time left.",
                "Agla mod, rasta ya bacha time poochiye.",
                "ಮುಂದಿನ ತಿರುವು, ದಾರಿ ಅಥವಾ ಸಮಯ ಕೇಳಿ.",
                hi_dev="अगला मोड़, रास्ता या बचा समय पूछिए।",
            ), has_loc=False)
        return reply(pick(
            "I can tell you the next turn, whether you are on the route, how far or how long is left, "
            "or repeat the last answer.",
            "Main agla mod, kya aap sahi raste par hain, kitni door ya kitna time bacha hai, "
            "ya pichla jawab dohra sakta hoon.",
            "ಮುಂದಿನ ತಿರುವು, ಸರಿಯಾದ ದಾರಿಯಲ್ಲಿದ್ದೀರಾ, ಇನ್ನು ಎಷ್ಟು ದೂರ ಅಥವಾ ಸಮಯವಿದೆ ಎಂದು ನಾನು ಹೇಳಬಲ್ಲೆ, "
            "ಅಥವಾ ಹಿಂದಿನ ಉತ್ತರವನ್ನು ಪುನರಾವರ್ತಿಸಬಹುದು.",
            hi_dev="मैं अगला मोड़, क्या आप सही रास्ते पर हैं, कितनी दूर या कितना समय बचा है बता सकता हूँ, या पिछला जवाब दोहरा सकता हूँ।",
        ), has_loc=False)

    if intent == "repeat":
        if s.last_answer:
            text, saved_lang = s.last_answer
            return ChatResponse(intent="repeat", lang=saved_lang, text=text, has_location=True)
        intent = "next_turn"  # nothing to repeat yet, so give the current instruction

    st = _fresh_status(s)
    if st is None:
        return reply(pick(
            "I do not have your current location yet. Start moving and ask again.",
            "Mujhe abhi aapki location nahi mil rahi hai. Thoda chalke phir poochiye.",
            "ನಿಮ್ಮ ಪ್ರಸ್ತುತ ಸ್ಥಳ ಇನ್ನೂ ಸಿಕ್ಕಿಲ್ಲ. ಸ್ವಲ್ಪ ಮುಂದೆ ಹೋಗಿ ಮತ್ತೆ ಕೇಳಿ.",
            hi_dev="मुझे अभी आपकी लोकेशन नहीं मिल रही है। थोड़ा चलकर फिर पूछिए।",
        ), has_loc=False)

    if st.arrived:
        return reply(pick(
            "You have arrived at your destination.",
            "Aap apni manzil par pahunch gaye hain.",
            "ನೀವು ನಿಮ್ಮ ಗಮ್ಯಸ್ಥಾನವನ್ನು ತಲುಪಿದ್ದೀರಿ.",
            hi_dev="आप अपनी मंज़िल पर पहुँच गए हैं।",
        ), remember=True)

    if intent == "arrived_check":
        if driver_mode:
            val, unit = round_spoken_distance(st.remaining_m)
            d_str = format_spoken_dist(val, unit, reply_lang)
            return reply(pick(
                f"Not yet. {d_str} to go.",
                f"Abhi nahi. {d_str} bache hain.",
                f"ಇನ್ನೂ ಇಲ್ಲ. ಇನ್ನು {d_str} ಹೋಗಬೇಕು.",
                hi_dev=f"अभी नहीं। {d_str} बाकी हैं।",
            ), remember=True)
        return reply(pick(
            f"Not yet. {fmt_dist(st.remaining_m)} to go.",
            f"Abhi nahi. {fmt_dist_hi(st.remaining_m)} aur chalna hai.",
            f"ಇನ್ನೂ ಇಲ್ಲ. ಇನ್ನು {fmt_dist_kn(st.remaining_m)} ಹೋಗಬೇಕು.",
            hi_dev=f"अभी नहीं। {fmt_dist_hi_dev(st.remaining_m)} और चलना बाकी है।",
        ), remember=True)

    if intent == "on_route":
        if st.on_route:
            return reply(pick(
                "Yes, you are on the right route.",
                "Haan, aap sahi raste par hain.",
                "ಹೌದು, ನೀವು ಸರಿಯಾದ ದಾರಿಯಲ್ಲಿದ್ದೀರಿ.",
                hi_dev="हाँ, आप सही रास्ते पर हैं।",
            ), remember=True)
        if driver_mode:
            val, unit = round_spoken_distance(st.distance_from_route_m)
            d_str = format_spoken_dist(val, unit, reply_lang)
            return reply(pick(
                f"No, off route by {d_str}.",
                f"Nahi, route se {d_str} door hain.",
                f"ಇಲ್ಲ, ದಾರಿಯಿಂದ {d_str} ದೂರದಲ್ಲಿದ್ದೀರಿ.",
                hi_dev=f"नहीं, रास्ते से {d_str} दूर हैं।",
            ), remember=True)
        return reply(pick(
            f"No, you are about {fmt_dist(st.distance_from_route_m)} off the route.",
            f"Nahi, aap route se lagbhag {fmt_dist_hi(st.distance_from_route_m)} door hain.",
            f"ಇಲ್ಲ, ನೀವು ದಾರಿಯಿಂದ ಸುಮಾರು {fmt_dist_kn(st.distance_from_route_m)} ದೂರದಲ್ಲಿದ್ದೀರಿ.",
            hi_dev=f"नहीं, आप रास्ते से लगभग {fmt_dist_hi_dev(st.distance_from_route_m)} दूर हैं।",
        ), remember=True)

    if intent == "time_left":
        n = max(1, round(st.remaining_s / 60))
        if driver_mode:
            val, unit = round_spoken_distance(st.remaining_m)
            d_str = format_spoken_dist(val, unit, reply_lang)
            return reply(pick(
                f"About {n} minutes and {d_str} to go.",
                f"Lagbhag {n} minute aur {d_str} bache hain.",
                f"ಸುಮಾರು {n} ನಿಮಿಷ ಮತ್ತು {d_str} ಬಾಕಿ ಇದೆ.",
                hi_dev=f"लगभग {n} मिनट और {d_str} बाकी हैं।",
            ), remember=True)
        return reply(pick(
            f"About {n} minutes left, {fmt_dist(st.remaining_m)} to go.",
            f"Lagbhag {n} minute bache hain, {fmt_dist_hi(st.remaining_m)} aur chalna hai.",
            f"ಸುಮಾರು {n} ನಿಮಿಷ ಬಾಕಿ ಇದೆ, {fmt_dist_kn(st.remaining_m)} ಹೋಗಬೇಕು.",
            hi_dev=f"लगभग {n} मिनट और {fmt_dist_hi_dev(st.remaining_m)} चलना बाकी है।",
        ), remember=True)

    if intent == "distance_left":
        if driver_mode:
            val, unit = round_spoken_distance(st.remaining_m)
            d_str = format_spoken_dist(val, unit, reply_lang)
            return reply(pick(
                f"{d_str} to go.",
                f"{d_str} bache hain.",
                f"ಇನ್ನು {d_str} ಹೋಗಬೇಕು.",
                hi_dev=f"{d_str} बाकी हैं।",
            ), remember=True)
        return reply(pick(
            f"{fmt_dist(st.remaining_m)} to go.",
            f"{fmt_dist_hi(st.remaining_m)} aur chalna hai.",
            f"ಇನ್ನು {fmt_dist_kn(st.remaining_m)} ಹೋಗಬೇಕು.",
            hi_dev=f"{fmt_dist_hi_dev(st.remaining_m)} और चलना बाकी है।",
        ), remember=True)

    if intent in ("traffic_ahead", "delay", "incident"):
        tsnap = s.traffic_snapshot
        if not tsnap or not tsnap.summary:
            return reply(pick(
                "Traffic information is not available.",
                "Traffic ki jaankari uplabdh nahi hai.",
                "ಟ್ರಾಫಿಕ್ ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ.",
                hi_dev="ट्रैफिक की जानकारी उपलब्ध नहीं है।",
            ), remember=True)

        if tsnap.is_stale():
            return reply(pick(
                "Traffic information is outdated, checked over 10 minutes ago.",
                "Traffic data purana hai, 10 minute se zyada purana.",
                "ಟ್ರಾಫಿಕ್ ಮಾಹಿತಿ ಹಳೆಯದಾಗಿದೆ, 10 ನಿಮಿಷಕ್ಕಿಂತ ಹಿಂದಿನದು.",
                hi_dev="ट्रैफिक डेटा पुराना है, 10 मिनट से ज़्यादा पुराना।",
            ), remember=True)

        summary = tsnap.summary
        age_m = summary.age_minutes()
        age_en = "just now" if age_m == 0 else f"{age_m} minutes ago"
        age_hi = "abhi" if age_m == 0 else f"{age_m} minute pehle"
        age_kn = "ಈಗಷ್ಟೇ" if age_m == 0 else f"{age_m} ನಿಮಿಷದ ಹಿಂದೆ"
        age_hi_dev = "अभी" if age_m == 0 else f"{age_m} मिनट पहले"

        if intent == "traffic_ahead":
            lvl = summary.level.value
            delay_m = summary.delay_minutes
            if lvl == "none" or delay_m == 0:
                return reply(pick(
                    f"Traffic is flowing smoothly, checked {age_en}.",
                    f"Traffic smooth hai, {age_hi} check kiya gaya.",
                    f"ಟ್ರಾಫಿಕ್ ಸುಗಮವಾಗಿದೆ, {age_kn} ಪರಿಶೀಲಿಸಲಾಗಿದೆ.",
                    hi_dev=f"ट्रैफिक सामान्य है, {age_hi_dev} चेक किया गया।",
                ), remember=True)
            lvl_hi = "bhaari" if lvl == "heavy" else "halka"
            lvl_kn = "ದಟ್ಟವಾಗಿದೆ" if lvl == "heavy" else "ಲಘುವಾಗಿದೆ"
            lvl_hi_dev = "भारी" if lvl == "heavy" else "हल्का"
            return reply(pick(
                f"Traffic is {lvl}, about {delay_m} minutes delay, checked {age_en}.",
                f"Traffic {lvl_hi} hai, lagbhag {delay_m} minute delay hai, {age_hi} check kiya.",
                f"ಟ್ರಾಫಿಕ್ {lvl_kn}, ಸುಮಾರು {delay_m} ನಿಮಿಷ ತಡ, {age_kn} ಪರಿಶೀಲಿಸಲಾಗಿದೆ.",
                hi_dev=f"ट्रैफिक {lvl_hi_dev} है, लगभग {delay_m} मिनट देरी है, {age_hi_dev} चेक किया गया।",
            ), remember=True)

        if intent == "delay":
            delay_m = summary.delay_minutes
            if delay_m == 0:
                return reply(pick(
                    f"No traffic delay, checked {age_en}.",
                    f"Koi delay nahi hai, {age_hi} check kiya gaya.",
                    f"ಯಾವುದೇ ತಡವಿಲ್ಲ, {age_kn} ಪರಿಶೀಲಿಸಲಾಗಿದೆ.",
                    hi_dev=f"कोई ट्रैफिक देरी नहीं है, {age_hi_dev} चेक किया गया।",
                ), remember=True)
            return reply(pick(
                f"About {delay_m} minutes delay, checked {age_en}.",
                f"Lagbhag {delay_m} minute ka delay hai, {age_hi} check kiya gaya.",
                f"ಸುಮಾರು {delay_m} ನಿಮಿಷ ತಡ, {age_kn} ಪರಿಶೀಲಿಸಲಾಗಿದೆ.",
                hi_dev=f"लगभग {delay_m} मिनट की देरी है, {age_hi_dev} चेक किया गया।",
            ), remember=True)

        if intent == "incident":
            along_m = (s.route.distance_m - st.remaining_m) if st else 0.0
            incidents_ahead = filter_incidents_on_route(tsnap.incidents, s.route.geometry, along_m)
            if not incidents_ahead:
                return reply(pick(
                    f"No incidents reported on route, checked {age_en}.",
                    f"Route par koi incident nahi hai, {age_hi} check kiya.",
                    f"ದಾರಿಯಲ್ಲಿ ಯಾವುದೇ ಅಪಘಾತ ವರದಿಯಾಗಿಲ್ಲ, {age_kn} ಪರಿಶೀಲಿಸಲಾಗಿದೆ.",
                    hi_dev=f"रास्ते पर कोई घटना या दुर्घटना दर्ज नहीं है।",
                ), remember=True)
            first_inc = incidents_ahead[0]
            val, unit = round_spoken_distance(first_inc.distance_to_user_m)
            d_str = format_spoken_dist(val, unit, reply_lang)
            inc_cat_kn = {
                "Accident": "ಅಪಘಾತ",
                "Jam": "ಟ್ರಾಫಿಕ್ ಜಾಮ್",
                "Road Works": "ರಸ್ತೆ ಕಾಮಗಾರಿ",
                "Closed": "ರಸ್ತೆ ಬಂದ್",
            }.get(first_inc.category, first_inc.category)
            inc_cat_hi = {
                "Accident": "दुर्घटना",
                "Jam": "ट्रैफिक जाम",
                "Road Works": "सड़क निर्माण",
                "Closed": "सड़क बंद",
            }.get(first_inc.category, first_inc.category)
            return reply(pick(
                f"{first_inc.category} reported {d_str} ahead.",
                f"{d_str} aage {first_inc.category} reported hai.",
                f"{d_str} ಮುಂದೆ {inc_cat_kn} ವರದಿಯಾಗಿದೆ.",
                hi_dev=f"आगे {d_str} पर {inc_cat_hi} दर्ज है।",
            ), remember=True)

    # next_turn
    if st.next_index is None or st.distance_to_next_m is None:
        if not st.on_route:
            return reply(pick(
                "You are off the route right now, so I cannot give the next turn yet.",
                "Aap abhi route se hat gaye hain, isliye agla mod abhi nahi bata sakta.",
                "ನೀವು ಈಗ ದಾರಿಯಿಂದ ಹೊರಗಿದ್ದೀರಿ, ಆದ್ದರಿಂದ ಮುಂದಿನ ತಿರುವು ಹೇಳಲು ಸಾಧ್ಯವಿಲ್ಲ.",
                hi_dev="आप अभी रास्ते से हट गए हैं, इसलिए अगला मोड़ अभी नहीं बता सकता।",
            ), remember=True)
        return reply(pick(
            "I cannot find the next turn right now.",
            "Mujhe agla mod abhi nahi mil raha.",
            "ಮುಂದಿನ ತಿರುವು ಈಗ ಸಿಗುತ್ತಿಲ್ಲ.",
            hi_dev="मुझे अगला मोड़ अभी नहीं मिल रहा।",
        ))

    step = s.route.steps[st.next_index]
    lm = s.landmarks.get(st.next_index)
    landmark = lm["name"] if lm else None

    if driver_mode:
        cfg = AnnouncerConfig(enable_kannada_driver=True)
        text = build_driver_instruction(
            stage="near",
            step=step,
            distance_to_next_m=st.distance_to_next_m,
            landmark_name=landmark,
            lang=reply_lang,
            config=cfg,
        )
        return reply(text, remember=True)

    if reply_lang == "kn":
        text = next_kannada(step, st.distance_to_next_m, landmark)
    elif reply_lang == "hi":
        text = next_hindi_devanagari(step, st.distance_to_next_m, landmark)
    elif reply_lang == "hinglish":
        text = next_hinglish(step, st.distance_to_next_m, landmark)
    else:
        text = live_instruction(step, st.distance_to_next_m, landmark)
    return reply(text, remember=True)
