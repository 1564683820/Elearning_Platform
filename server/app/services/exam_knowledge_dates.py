"""Translate teacher-facing calendar dates to UTC boundaries for grading queries."""
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone


BEIJING_TIME = timezone(timedelta(hours=8))
DAY = r"(?:\d{4}-\d{1,2}-\d{1,2}|(?:\d{4}年)?\d{1,2}月\d{1,2}[日号])"
CALENDAR_DAY = re.compile(DAY)
RANGE = re.compile(rf"(?P<start>{DAY})\s*(?:到|至|~|～|—|–|\s-\s)\s*(?P<end>{DAY})")
ROLLING = re.compile(r"(?:最近|过去|近)\s*(\d{1,4})\s*天")
RELATIVE = re.compile(r"今天|今日|昨天|昨日|前天|本周|这周|上周|本月|这个月|上个月|上月")


@dataclass(frozen=True)
class ExamKnowledgePeriod:
    start: date
    end: date

    def __post_init__(self):
        if self.start.year < 1000 or self.start > self.end or self.end == date.max:
            raise ValueError("日期范围无效")

    @property
    def bounds(self) -> tuple[datetime, datetime]:
        def midnight(day: date) -> datetime:
            return datetime.combine(day, time.min, BEIJING_TIME).astimezone(timezone.utc).replace(tzinfo=None)

        return midnight(self.start), midnight(self.end + timedelta(days=1))

    def fields(self) -> dict[str, str]:
        return {"date_from": self.start.isoformat(), "date_to": self.end.isoformat()}


def _calendar_day(text: str, year: int) -> date:
    parts = [int(value) for value in re.findall(r"\d+", text)]
    return date(year, *parts) if len(parts) == 2 else date(*parts)


def _normalize_dates(text: str) -> str:
    return re.sub(r"(?<=\d)\s+(?=[年月日号])|(?<=[年月])\s+(?=\d)", "", text)


def is_exam_period_followup(text: str) -> bool:
    normalized = _normalize_dates(text)
    for pattern in (RANGE, CALENDAR_DAY, ROLLING, RELATIVE):
        remainder, count = pattern.subn("", normalized)
        if count and re.fullmatch(r"(?:那|那就|只看|看)?\s*(?:的)?\s*(?:呢)?[？?。！!\s]*", remainder):
            return True
    return False


def parse_exam_period(text: str, *, at: datetime | None = None) -> ExamKnowledgePeriod | None:
    at = at or datetime.now(timezone.utc)
    today = (at if at.tzinfo else at.replace(tzinfo=timezone.utc)).astimezone(BEIJING_TIME).date()
    text = _normalize_dates(text)
    ranges = list(RANGE.finditer(text))
    remainder = RANGE.sub("", text)
    days = list(CALENDAR_DAY.finditer(remainder))
    rolling_days = list(ROLLING.finditer(remainder))
    relative_periods = list(RELATIVE.finditer(remainder))
    if len(ranges) + len(days) + len(rolling_days) + len(relative_periods) > 1:
        raise ValueError("请提供单一日期或一个连续的日期范围")
    if ranges:
        start = _calendar_day(ranges[0]["start"], today.year)
        end = _calendar_day(ranges[0]["end"], start.year)
        return ExamKnowledgePeriod(start, end)
    if rolling_days:
        return ExamKnowledgePeriod(today - timedelta(days=int(rolling_days[0][1]) - 1), today)
    if days:
        exact = _calendar_day(days[0][0], today.year)
        return ExamKnowledgePeriod(exact, exact)
    monday = today - timedelta(days=today.weekday())
    month = today.replace(day=1)
    previous_month_end = month - timedelta(days=1)
    if not relative_periods:
        return None
    start, end = {
        "今天": (today, today), "今日": (today, today),
        "昨天": (today - timedelta(days=1), today - timedelta(days=1)),
        "昨日": (today - timedelta(days=1), today - timedelta(days=1)),
        "前天": (today - timedelta(days=2), today - timedelta(days=2)),
        "本周": (monday, today), "这周": (monday, today),
        "上周": (monday - timedelta(days=7), monday - timedelta(days=1)),
        "本月": (month, today), "这个月": (month, today),
        "上个月": (previous_month_end.replace(day=1), previous_month_end),
        "上月": (previous_month_end.replace(day=1), previous_month_end),
    }[relative_periods[0][0]]
    return ExamKnowledgePeriod(start, end)
