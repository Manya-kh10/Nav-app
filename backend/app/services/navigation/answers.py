import time

from app.schemas.chat import ChatResponse
from app.schemas.route import Step
from app.services.intent.classifier import classify
from app.services.navigation.sessions import Session
from app.services.navigation.templates import fmt_dist, live_instruction

STALE_S = 30  # a position older than this is not used to answer
ROUNDABOUT = ("roundabout", "rotary", "roundabout turn", "exit roundabout", "exit rotary")
HI_DIR = {
    "left": "left", "right": "right", "slight left": "thoda left", "slight right": "thoda right",
    "sharp left": "tez left", "sharp right": "tez right", "straight": "seedha", "uturn": "U-turn",
}
KN_DIR = {
    "left": "ಎಡಕ್ಕೆ", "right": "ಬಲಕ್ಕೆ", "slight left": "ಸ್ವಲ್ಪ ಎಡಕ್ಕೆ", "slight right": "ಸ್ವಲ್ಪ ಬಲಕ್ಕೆ",
    "sharp left": "ಪೂರ್ತಿ ಎಡಕ್ಕೆ", "sharp right": "ಪೂರ್ತಿ ಬಲಕ್ಕೆ", "straight": "ನೇರವಾಗಿ", "uturn": "ಯು-ಟರ್ನ್",
}


def fmt_dist_hi(m: float) -> str:
    r = max(10, int(round(m / 10.0)) * 10)
    if r < 1000:
        return f"{r} meter"
    return f"{round(m / 1000, 1):g} kilometer"


def fmt_dist_kn(m: float) -> str:
    r = max(10, int(round(m / 10.0)) * 10)
    if r < 1000:
        return f"{r} ಮೀಟರ್"
    return f"{round(m / 1000, 1):g} ಕಿಲೋಮೀಟರ್"


def next_hinglish(step: Step, dist_m: float, landmark: str | None) -> str:
    d = fmt_dist_hi(dist_m)
    if step.maneuver == "arrive":
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
    text = f"{d} ke baad {road}{action}"
    if landmark:
        text += f", {landmark} ke paas"
    return text + "."


def next_kannada(step: Step, dist_m: float, landmark: str | None) -> str:
    d = fmt_dist_kn(dist_m)
    if step.maneuver == "arrive":
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
    text = f"{d} ನಂತರ {road}{action}"
    if landmark:
        text += f", {landmark} ಹತ್ತಿರ"
    return text + "."


def _fresh_status(s: Session):
    if s.last_status is None:
        return None
    if s.last_status.arrived:
        return s.last_status
    if time.time() - s.last_status_at > STALE_S:
        return None
    return s.last_status


def answer(s: Session, message: str) -> ChatResponse:
    intent, lang = classify(message)
    if lang == "kn":
        reply_lang = "kn"
    elif lang == "hinglish":
        reply_lang = "hinglish"
    else:
        reply_lang = "en"

    def pick(en: str, hin: str, kn: str) -> str:
        if reply_lang == "kn":
            return kn
        if reply_lang == "hinglish":
            return hin
        return en

    def reply(text: str, has_loc: bool = True, remember: bool = False) -> ChatResponse:
        if remember:
            s.last_answer = (text, reply_lang)
        return ChatResponse(intent=intent, lang=reply_lang, text=text, has_location=has_loc)

    if intent == "unknown":
        return reply(pick(
            "I can tell you the next turn, whether you are on the route, how far or how long is left, "
            "or repeat the last answer.",
            "Main agla mod, kya aap sahi raste par hain, kitni door ya kitna time bacha hai, "
            "ya pichla jawab dohra sakta hoon.",
            "ಮುಂದಿನ ತಿರುವು, ಸರಿಯಾದ ದಾರಿಯಲ್ಲಿದ್ದೀರಾ, ಇನ್ನು ಎಷ್ಟು ದೂರ ಅಥವಾ ಸಮಯವಿದೆ ಎಂದು ನಾನು ಹೇಳಬಲ್ಲೆ, "
            "ಅಥವಾ ಹಿಂದಿನ ಉತ್ತರವನ್ನು ಪುನರಾವರ್ತಿಸಬಹುದು.",
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
        ), has_loc=False)

    if st.arrived:
        return reply(pick(
            "You have arrived at your destination.",
            "Aap apni manzil par pahunch gaye hain.",
            "ನೀವು ನಿಮ್ಮ ಗಮ್ಯಸ್ಥಾನವನ್ನು ತಲುಪಿದ್ದೀರಿ.",
        ), remember=True)

    if intent == "arrived_check":
        return reply(pick(
            f"Not yet. {fmt_dist(st.remaining_m)} to go.",
            f"Abhi nahi. {fmt_dist_hi(st.remaining_m)} aur chalna hai.",
            f"ಇನ್ನೂ ಇಲ್ಲ. ಇನ್ನು {fmt_dist_kn(st.remaining_m)} ಹೋಗಬೇಕು.",
        ), remember=True)

    if intent == "on_route":
        if st.on_route:
            return reply(pick(
                "Yes, you are on the right route.",
                "Haan, aap sahi raste par hain.",
                "ಹೌದು, ನೀವು ಸರಿಯಾದ ದಾರಿಯಲ್ಲಿದ್ದೀರಿ.",
            ), remember=True)
        return reply(pick(
            f"No, you are about {fmt_dist(st.distance_from_route_m)} off the route.",
            f"Nahi, aap route se lagbhag {fmt_dist_hi(st.distance_from_route_m)} door hain.",
            f"ಇಲ್ಲ, ನೀವು ದಾರಿಯಿಂದ ಸುಮಾರು {fmt_dist_kn(st.distance_from_route_m)} ದೂರದಲ್ಲಿದ್ದೀರಿ.",
        ), remember=True)

    if intent == "time_left":
        n = max(1, round(st.remaining_s / 60))
        return reply(pick(
            f"About {n} minutes left, {fmt_dist(st.remaining_m)} to go. This does not include traffic.",
            f"Lagbhag {n} minute bache hain, {fmt_dist_hi(st.remaining_m)} aur chalna hai. "
            f"Isme traffic shamil nahi hai.",
            f"ಸುಮಾರು {n} ನಿಮಿಷ ಬಾಕಿ ಇದೆ, {fmt_dist_kn(st.remaining_m)} ಹೋಗಬೇಕು. "
            f"ಇದರಲ್ಲಿ ಟ್ರಾಫಿಕ್ ಸೇರಿಲ್ಲ.",
        ), remember=True)

    if intent == "distance_left":
        return reply(pick(
            f"{fmt_dist(st.remaining_m)} to go.",
            f"{fmt_dist_hi(st.remaining_m)} aur chalna hai.",
            f"ಇನ್ನು {fmt_dist_kn(st.remaining_m)} ಹೋಗಬೇಕು.",
        ), remember=True)

    # next_turn
    if st.next_index is None or st.distance_to_next_m is None:
        if not st.on_route:
            return reply(pick(
                "You are off the route right now, so I cannot give the next turn yet.",
                "Aap abhi route se hat gaye hain, isliye agla mod abhi nahi bata sakta.",
                "ನೀವು ಈಗ ದಾರಿಯಿಂದ ಹೊರಗಿದ್ದೀರಿ, ಆದ್ದರಿಂದ ಮುಂದಿನ ತಿರುವು ಹೇಳಲು ಸಾಧ್ಯವಿಲ್ಲ.",
            ), remember=True)
        return reply(pick(
            "I cannot find the next turn right now.",
            "Mujhe agla mod abhi nahi mil raha.",
            "ಮುಂದಿನ ತಿರುವು ಈಗ ಸಿಗುತ್ತಿಲ್ಲ.",
        ))

    step = s.route.steps[st.next_index]
    lm = s.landmarks.get(st.next_index)
    landmark = lm["name"] if lm else None
    if reply_lang == "kn":
        text = next_kannada(step, st.distance_to_next_m, landmark)
    elif reply_lang == "hinglish":
        text = next_hinglish(step, st.distance_to_next_m, landmark)
    else:
        text = live_instruction(step, st.distance_to_next_m, landmark)
    return reply(text, remember=True)
