"""Shared objective-paper grading using the same numbering as printed answer sheets."""
from app.services.exam_service import ExamService


def grade_choice_answers(questions: list, marked_answers: dict, start_number: int = 1):
    entries = ExamService._extract_choice_questions(questions, start_number=start_number)
    numbers = [entry['question_number'] for entry in entries]
    if len(numbers) != len(set(numbers)):
        raise ValueError('试卷选择题题号重复，请先修正试卷')
    answers = []
    details = []
    total = 0
    for entry in entries:
        number = entry['question_number']
        marked = marked_answers.get(str(number), marked_answers.get(number, ''))
        confidence = 1.0
        if isinstance(marked, dict):
            confidence = marked.get('confidence', 0)
            marked = marked.get('student_answer', '')
        if isinstance(marked, list):
            marked = ''.join(str(value) for value in marked)
        selected = str(marked or '').strip().upper()
        correct = entry['correct_answer']
        if entry['question_type'] == 'multiple_choice':
            is_correct = bool(selected and correct) and set(selected) == set(correct)
        else:
            is_correct = bool(selected and correct) and selected == correct
        maximum = entry['score']
        score = maximum if is_correct else 0
        total += score
        answers.append({
            'question_number': number, 'student_answer': selected,
            'correct_answer': correct, 'is_correct': is_correct,
            'score': score, 'max_score': maximum, 'confidence': confidence,
        })
        source = questions[entry['source_index']]
        details.append({
            'index': entry['source_index'], 'question_number': number,
            'sub_index': entry.get('sub_index'), 'type': source.get('type', 'choice'),
            'stem': source.get('stem', ''), 'user_answer': selected,
            'correct_answer': correct, 'is_correct': is_correct,
            'score': score, 'max_score': maximum,
        })
    return answers, details, total
