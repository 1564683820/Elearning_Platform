import unittest
from app.services.paper_grading import grade_choice_answers


class PaperGradingTests(unittest.TestCase):
    def test_non_choice_questions_reserve_their_printed_numbers(self):
        answers, _, _ = grade_choice_answers([
            {'type': 'writing'},
            {'type': 'grammar_fill', 'answers': ['word', 'word']},
            {'answer': 'A', 'score': 2},
        ], {'4': 'A'})
        self.assertEqual(answers[0]['question_number'], 4)
        self.assertTrue(answers[0]['is_correct'])

    def test_high_school_reading_cloze_and_multiple_share_printed_numbers(self):
        questions = [
            {'type': 'reading', 'score': 4, 'sub_questions': [{'answer': 'A'}, {'answer': 'B'}]},
            {'type': 'cloze', 'answers': ['C', 'D'], 'score': 3},
            {'type': 'multiple', 'answer': ['A', 'C'], 'score': 2},
        ]
        answers, details, total = grade_choice_answers(questions, {'21': 'A', '22': 'B', '23': 'C', '24': 'D', '25': 'CA'}, 21)
        self.assertEqual(total, 9)
        self.assertEqual([a['question_number'] for a in answers], [21, 22, 23, 24, 25])
        self.assertEqual([a['index'] for a in details], [0, 0, 1, 1, 2])
        self.assertEqual(details[1]['sub_index'], 1)

    def test_stored_numbers_and_unanswered_questions_are_preserved(self):
        answers, _, total = grade_choice_answers([
            {'type': 'single', 'question_number': 31, 'answer': 'B', 'score': 2},
            {'type': 'single', 'question_number': 35, 'answer': 'A', 'score': 3},
        ], {31: {'student_answer': 'b', 'confidence': 0.9}})
        self.assertEqual(total, 2)
        self.assertEqual(answers[1]['question_number'], 35)
        self.assertFalse(answers[1]['is_correct'])
        self.assertEqual(answers[0]['confidence'], 0.9)
