from typing import Annotated

from pydantic import BaseModel, Field


class PaperDraftIn(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    description: str = Field("", max_length=512)
    class_id: int = Field(0, ge=0)
    template_id: int | None = Field(None, gt=0)
    template_revision: str | None = Field(None, max_length=64)
    revision: str | None = Field(None, max_length=64)
    question_numbers: list[Annotated[int, Field(strict=True, gt=0, le=9007199254740991)]] | None = Field(
        None, max_length=300,
    )
    answers: dict[int, str] = Field(default_factory=dict, max_length=300)
    finalize: bool = False


class PaperDraftCopyIn(BaseModel):
    request_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class PaperDraftCreateIn(PaperDraftIn):
    request_id: str | None = Field(None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class PaperDraftQuestion(BaseModel):
    question_number: int
    score: int
    options: list[str]
    answer: str


class PaperDraftOut(BaseModel):
    id: str
    title: str
    description: str
    class_id: str
    template_id: str | None
    template_revision: str | None
    template_name: str | None
    revision: str
    paper_draft: bool
    layout_configured: bool = False
    questions: list[PaperDraftQuestion]
    created_revision: str | None = None
