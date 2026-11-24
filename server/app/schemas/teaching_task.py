"""Strict, bounded artifacts shared by generation, teacher editing and publishing."""
from typing import Annotated, Literal
from pydantic import BaseModel, Field, StringConstraints

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class TeachingQuestion(BaseModel):
    type: Literal['choice'] = 'choice'
    stem: ShortText
    options: list[ShortText] = Field(min_length=4, max_length=4)
    answer: Literal['A', 'B', 'C', 'D']
    explanation: ShortText
    score: int = Field(ge=1, le=100)
    knowledge_point: ShortText
    citation_ids: list[str] = Field(min_length=1, max_length=10)


class LessonStep(BaseModel):
    title: ShortText
    minutes: int = Field(ge=1, le=120)
    activity: ShortText


class TeachingArtifact(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
    lesson: list[LessonStep] = Field(min_length=1, max_length=20)
    questions: list[TeachingQuestion] = Field(min_length=1, max_length=30)
    total_score: int = Field(ge=1, le=3000)


def validate_artifact(value: dict, checkpoint: dict) -> TeachingArtifact:
    artifact = TeachingArtifact.model_validate(value)
    config = checkpoint.get('config', {})
    if len(artifact.questions) != config.get('question_count', 10):
        raise ValueError('题目数量与任务设置不一致')
    if sum(step.minutes for step in artifact.lesson) != config.get('duration_minutes', 20):
        raise ValueError('教案总时长与任务设置不一致')
    if sum(q.score for q in artifact.questions) != artifact.total_score:
        raise ValueError('题目分数之和与总分不一致')
    stems = [''.join(q.stem.lower().split()) for q in artifact.questions]
    if len(set(stems)) != len(stems):
        raise ValueError('存在重复题目')
    sources = {str(c['id']) for c in checkpoint.get('citations', [])}
    topics = {t['knowledge_point'] for t in checkpoint.get('analysis', {}).get('topics', [])}
    covered = set()
    for question in artifact.questions:
        if not set(question.citation_ids).issubset(sources):
            raise ValueError('题目引用了不存在的教材证据')
        if len(set(o.strip().casefold() for o in question.options)) != 4:
            raise ValueError('同一道题的选项重复')
        if question.knowledge_point not in topics:
            raise ValueError('题目知识点缺少班级错题统计支持')
        covered.add(question.knowledge_point)
    if not topics.issubset(covered):
        raise ValueError('练习未覆盖全部目标薄弱知识点')
    return artifact
