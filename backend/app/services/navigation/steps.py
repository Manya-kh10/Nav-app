from app.schemas.route import Step

MIN_STEP_M = 15  # tunable: shorter segments are usually mapping artifacts, not real turns


def simplify_steps(steps: list[Step]) -> list[Step]:
    out: list[Step] = []
    for s in steps:
        edge = s.maneuver in ("depart", "arrive")
        if out and not edge and s.distance_m < MIN_STEP_M:
            prev = out[-1]
            out[-1] = prev.model_copy(update={
                "distance_m": prev.distance_m + s.distance_m,
                "duration_s": prev.duration_s + s.duration_s,
            })
            continue
        out.append(s)
    return out