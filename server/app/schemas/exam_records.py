from datetime import datetime
from typing import Literal

from pydantic import BaseModel


RecordStatus = Literal["confirmed", "review", "failed", "historical"]


class GradingRecordItem(BaseModel):
    id: str
    exam_number: str
    student_name: str
    score: float | None
    max_score: float | None
    status: RecordStatus
    source: Literal["manual", "scan", "online", "legacy_scan"]
    updated_at: datetime | None
    record_kind: Literal["submission", "scan"] = "submission"


class GradingRecordsOut(BaseModel):
    title: str
    total: int
    confirmed: int
    pending: int
    items: list[GradingRecordItem]


class RecordQuestion(BaseModel):
    number: int
    marked: str
    invalid_mark: bool = False
    raw: str | None
    answer: str
    score: float | None
    max_score: float


class GradingRecordHistory(BaseModel):
    id: str
    action: str
    created_at: datetime | None
    old_score: float | None
    new_score: float | None
    reason: str | None


class GradingRecordOut(GradingRecordItem):
    title: str
    has_photo: bool
    withdrawable_grade_version: int | None
    questions: list[RecordQuestion]
    history: list[GradingRecordHistory]
