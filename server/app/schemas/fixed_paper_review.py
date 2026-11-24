from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class PaperGradingStateIn(BaseModel):
    state: Literal["completed", "grading"]
    revision: int = Field(ge=0)


class PaperGradingStateOut(BaseModel):
    state: Literal["draft", "ready", "grading", "completed"]
    revision: int
    class_name: str | None
    layout_configured: bool
    recognition_available: bool
    recognition_blocker: str | None = None
    capture_aspect_ratio: float | None = None
    exam_title: str
    confirmed: int
    pending: int
    expected: int | None
    closed_at: datetime | None


class PaperRecognitionOut(BaseModel):
    state: Literal["review", "retake", "layout_mismatch"]
    scan_id: str


class PaperReviewConflictOut(BaseModel):
    detail: str
    error_code: Literal["paper_review_conflict"] | None = None


class PaperReviewDiscard(BaseModel):
    revision: str
    reason: str = Field(min_length=1, max_length=200)


class PaperGradeWithdraw(BaseModel):
    grade_version: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=200)


class PaperGradeRegrade(BaseModel):
    grade_version: int = Field(gt=0)
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")


class PaperReviewEdits(BaseModel):
    revision: str
    exam_number: str = Field(max_length=64)
    answers: dict[int, str] = Field(default_factory=dict, max_length=300)
    invalid_answers: dict[int, Annotated[list[str], Field(min_length=2, max_length=8)]] = Field(default_factory=dict, max_length=300)


class PaperReviewConfirm(BaseModel):
    revision: str
    previous_submission_id: int | None = None
    previous_grade_version: int | None = Field(None, ge=0)


class PreviousPaperGrade(BaseModel):
    submission_id: str
    grade_version: int
    score: int | None
    max_score: int | None
    withdrawn: bool


class PaperReviewQuestion(BaseModel):
    number: int
    marked: str
    raw_marked: str
    invalid_mark: bool
    answer: str
    options: list[str]
    score: int
    max_score: int
    needs_review: bool


class PaperReviewReceipt(BaseModel):
    submission_id: str
    grade_version: int
    score: int
    max_score: int


class PendingPaperReview(BaseModel):
    id: str
    exam_number: str
    recognized_count: int
    reason: str | None = None
    updated_at: datetime | None


class PendingPaperReviews(BaseModel):
    total: int
    items: list[PendingPaperReview]


class ExamNumberCellOut(BaseModel):
    position: int = Field(ge=1, le=64)
    state: Literal["read", "empty", "ambiguous", "unavailable"]
    digit: str | None = Field(None, pattern=r"^[0-9]$")
    confidence: float | None = Field(None, ge=0, le=1)


class PaperReviewOut(BaseModel):
    id: str
    status: str
    exam_title: str
    revision: str
    exam_number: str
    exam_number_length: int | None = None
    exam_number_cells: list[ExamNumberCellOut] | None = None
    exam_number_overflow: bool = False
    identity_conflict: str | None = None
    student_name: str | None
    class_required: bool
    class_id: str | None
    class_name: str | None
    has_photo: bool
    score: int
    max_score: int
    questions: list[PaperReviewQuestion]
    previous_grade: PreviousPaperGrade | None
    regrade_submission_id: str | None = None
    receipt: PaperReviewReceipt | None
    created_at: datetime | None
    updated_at: datetime | None
    reason: str | None = None
