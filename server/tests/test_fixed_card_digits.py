import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from app.services.fixed_card_digits import read_digits


class FixedCardDigitTests(unittest.TestCase):
    def setUp(self):
        self.blank = np.full((40, 30), 225, dtype=np.uint8)
        cv2.rectangle(self.blank, (0, 0), (29, 39), 50, 1)

    def ink(self, digit):
        photo = self.blank.copy()
        cv2.putText(photo, digit, (6, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 30, 2)
        return photo, self.blank

    @patch("app.services.fixed_card_digits._predict")
    def test_model_candidates_keep_positions_and_prefix_zero(self, predict):
        predict.return_value = np.eye(10, dtype=np.float32)[[0, 0, 7]]
        crops = [self.ink(digit) for digit in "007"]
        path = Path("fixture.onnx")
        number, cells, overflow = read_digits(crops, None, path, 0.9)
        self.assertEqual(number, "007")
        self.assertEqual([cell["position"] for cell in cells], [1, 2, 3])
        self.assertFalse(overflow)
        model, batch = predict.call_args.args
        self.assertEqual(model, path)
        self.assertEqual([image.shape for image in batch], [(28, 28)] * 3)
        number, cells, overflow = read_digits(crops, self.ink("4"), path, 0.9)
        self.assertEqual(number, "")
        self.assertTrue(overflow)
        self.assertEqual([cell["digit"] for cell in cells], list("007"))

    def test_blank_and_cross_grid_ink_preserve_unknown_positions(self):
        crosses_edge = self.blank.copy()
        cv2.line(crosses_edge, (18, 24), (29, 24), 20, 3)
        crops = [self.ink("0"), (self.blank, self.blank), (crosses_edge, self.blank)]
        number, cells, overflow = read_digits(crops, None, None, 0.9)
        self.assertEqual(number, "")
        self.assertFalse(overflow)
        self.assertEqual([cell["state"] for cell in cells], ["unavailable", "empty", "ambiguous"])
