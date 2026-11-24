from datetime import date

from pydantic import BaseModel, Field


class ExamKnowledgeAvailability(BaseModel):
    has_confirmed_results: bool


class ExamKnowledgeQuestion(BaseModel):
    number: int
    stem: str
    answer: str
    option_text: dict[str, str] = Field(default_factory=dict)
    correct: int
    distribution: dict[str, int]


class ExamKnowledgeOut(BaseModel):
    id: str
    title: str
    count: int
    average: float | None
    updated_at: str | None
    questions: list[ExamKnowledgeQuestion]
    date_from: date | None = None
    date_to: date | None = None
