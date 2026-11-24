"""Validate model grades before they become learning records."""
import json
import math
import re


class InvalidAIGradeError(ValueError):
    def __init__(self):
        super().__init__('AI 评分结果无效，请稍后重试，本次未记录成绩')


def validate_grade_result(result: object) -> dict:
    if not isinstance(result, dict):
        raise InvalidAIGradeError()
    score = result.get('score')
    if (isinstance(score, bool) or not isinstance(score, (int, float))
            or not 0 <= score <= 100 or not math.isfinite(score)):
        raise InvalidAIGradeError()
    return result


def parse_grade_result(response: str) -> dict:
    if not isinstance(response, str):
        raise InvalidAIGradeError()
    text = response.strip()
    if text.startswith('```'):
        match = re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if not match:
            raise InvalidAIGradeError()
        text = match.group(1)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        raise InvalidAIGradeError() from None
    return validate_grade_result(result)
