from pydantic import BaseModel


class Place(BaseModel):
    name: str
    display_name: str
    lat: float
    lon: float
    category: str | None = None
    type: str | None = None
    importance: float | None = None
    score: float | None = None     # 0-100 match score against what was typed or said
    source: str | None = None      # "local" or "online"
    name_kn: str | None = None     # Kannada script name
