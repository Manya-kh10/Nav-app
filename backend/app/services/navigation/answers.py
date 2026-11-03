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


def fmt_dist_hi(m: float) -> str:
    r = max(10, int(round(m / 10.0)) * 10)
    if r < 1000:
        return f"{r} meter"
    return f"{round(m / 1000, 1):g} kilometer"


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
    hi = lang == "hinglish"
    reply_lang = "hinglish" if hi else "en"

    def pick(en: str, hin: str) -> str:
        return hin if hi else en

    def reply(text: str, has_loc: bool = True, remember: bool = False) -> ChatResponse:
        if remember:
            s.last_answer = (text, reply_lang)
        return ChatResponse(intent=intent, lang=reply_lang, text=text, has_location=has_loc)

    if intent == "unsupported_language":
        return ChatResponse(
            intent=intent, lang="en", has_location=True,
            text="Kannada questions are not supported in text chat yet. Please ask in English or Hindi.",
        )

    if intent == "unknown":
        return reply(pick(
            "I can tell you the next turn, whether you are on the route, how far or how long is left, "
            "or repeat the last answer.",
            "Main agla mod, kya aap sahi raste par hain, kitni door ya kitna time bacha hai, "
            "ya pichla jawab dohra sakta hoon.",
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
        ), has_loc=False)

    if st.arrived:
        return reply(pick("You have arrived at your destination.",
                          "Aap apni manzil par pahunch gaye hain."), remember=True)

    if intent == "arrived_check":
        return reply(pick(
            f"Not yet. {fmt_dist(st.remaining_m)} to go.",
            f"Abhi nahi. {fmt_dist_hi(st.remaining_m)} aur chalna hai.",
        ), remember=True)

    if intent == "on_route":
        if st.on_route:
            return reply(pick("Yes, you are on the right route.",
                              "Haan, aap sahi raste par hain."), remember=True)
        return reply(pick(
            f"No, you are about {fmt_dist(st.distance_from_route_m)} off the route.",
            f"Nahi, aap route se lagbhag {fmt_dist_hi(st.distance_from_route_m)} door hain.",
        ), remember=True)

    if intent == "time_left":
        n = max(1, round(st.remaining_s / 60))
        return reply(pick(
            f"About {n} minutes left, {fmt_dist(st.remaining_m)} to go. This does not include traffic.",
            f"Lagbhag {n} minute bache hain, {fmt_dist_hi(st.remaining_m)} aur chalna hai. "
            f"Isme traffic shamil nahi hai.",
        ), remember=True)

    if intent == "distance_left":
        return reply(pick(
            f"{fmt_dist(st.remaining_m)} to go.",
            f"{fmt_dist_hi(st.remaining_m)} aur chalna hai.",
        ), remember=True)

    # next_turn
    if st.next_index is None or st.distance_to_next_m is None:
        if not st.on_route:
            return reply(pick(
                "You are off the route right now, so I cannot give the next turn yet.",
                "Aap abhi route se hat gaye hain, isliye agla mod abhi nahi bata sakta.",
            ), remember=True)
        return reply(pick("I cannot find the next turn right now.",
                          "Mujhe agla mod abhi nahi mil raha."))

    step = s.route.steps[st.next_index]
    lm = s.landmarks.get(st.next_index)
    landmark = lm["name"] if lm else None
    if hi:
        text = next_hinglish(step, st.distance_to_next_m, landmark)
    else:
        text = live_instruction(step, st.distance_to_next_m, landmark)
    return reply(text, remember=True)