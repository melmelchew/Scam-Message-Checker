from typing import Literal

from pydantic import BaseModel, Field

Label = Literal["scam", "suspicious", "legit"]


class Verdict(BaseModel):
    """Structured answer returned by the model for one message."""

    label: Label = Field(description="scam, suspicious, or legit")
    risk_score: int = Field(description="0 (clearly safe) to 100 (certain scam)")
    red_flags: list[str] = Field(description="Specific warning signs found in the message; empty if none")
    explanation: str = Field(description="One or two sentences explaining the verdict")
    advice: str = Field(description="What the recipient should do next")
