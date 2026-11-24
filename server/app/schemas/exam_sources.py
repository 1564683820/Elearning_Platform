from typing import Literal

from pydantic import BaseModel


class ExamSourceOut(BaseModel):
    id: str
    name: str
    size: int
    kind: Literal["pdf", "word", "image"]
    order: int
