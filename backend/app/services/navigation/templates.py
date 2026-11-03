from app.schemas.route import Instruction, Step

DIRS = {
    "left": "left", "right": "right",
    "slight left": "slightly left", "slight right": "slightly right",
    "sharp left": "sharply left", "sharp right": "sharply right",
    "straight": "straight", "uturn": "around",
}


def fmt_dist(m: float) -> str:
    r = max(10, int(round(m / 10.0)) * 10)
    if r < 1000:
        return f"{r} meters"
    km = round(m / 1000, 1)
    if km == int(km):
        n = int(km)
        return f"{n} kilometer" if n == 1 else f"{n} kilometers"
    return f"{km:g} kilometers"


def _action(step: Step) -> str:
    mod = step.modifier
    if step.maneuver in ("roundabout", "rotary", "roundabout turn", "exit roundabout", "exit rotary"):
        return "take the roundabout"
    if mod == "uturn":
        return "make a U-turn"
    if step.maneuver == "fork":
        side = (mod or "").replace("slight ", "")
        return f"keep {side}" if side in ("left", "right") else "continue"
    if step.maneuver == "end of road" and mod in DIRS:
        return f"at the end of the road, turn {DIRS[mod]}"
    if mod in DIRS:
        return "continue straight" if mod == "straight" else f"turn {DIRS[mod]}"
    return "continue"


def build_instructions(steps: list[Step], landmarks: dict[int, dict], mode: str) -> list[Instruction]:
    out: list[Instruction] = []
    for i, st in enumerate(steps):
        prev_dist = steps[i - 1].distance_m if i > 0 else 0.0
        lm = landmarks.get(i)
        if st.maneuver == "depart":
            verb = "walking" if mode == "walk" else "driving"
            text = f"Start {verb}. Continue for {fmt_dist(st.distance_m)}."
        elif st.maneuver == "arrive":
            text = f"After {fmt_dist(prev_dist)}, you will arrive at your destination."
        else:
            text = f"After {fmt_dist(prev_dist)}, {_action(st)}"
            if st.road and "roundabout" not in _action(st):
                text += f" onto {st.road}"
            if lm:
                text += f", near {lm['name']}"
            text += "."
        out.append(Instruction(
            text=text, maneuver=st.maneuver, modifier=st.modifier, distance_to_m=prev_dist,
            lat=st.lat, lon=st.lon,
            landmark=lm["name"] if lm else None, landmark_kind=lm["kind"] if lm else None,
        ))
    return out

def live_instruction(step: Step, dist_m: float, landmark: str | None) -> str:
    if step.maneuver == "arrive":
        return f"In {fmt_dist(dist_m)}, you will arrive at your destination."
    action = _action(step)
    text = f"In {fmt_dist(dist_m)}, {action}"
    if step.road and "roundabout" not in action:
        text += f" onto {step.road}"
    if landmark:
        text += f", near {landmark}"
    return text + "."