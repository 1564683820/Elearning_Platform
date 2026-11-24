# -*- coding: utf-8 -*-
"""端到端测试：使用修改后的omr_scanner扫描真实答题卡exam.jpg"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.omr_scanner import scan_answer_sheet, REAL_SHEET_COORDINATES

# 预期答案
EXPECTED = {
    1: "B", 2: "C", 3: "B", 4: "C", 5: "B",
    6: "B", 7: "C", 8: "B", 9: "C", 10: "C",
    11: "A", 12: "D",
    13: "", 14: "", 15: "", 16: "", 17: "", 18: "", 19: "", 20: "",
    21: "E", 22: "G", 23: "D", 24: "F", 25: "C",
}

# 加载真实答题卡
from pathlib import Path

image_path = str(Path(__file__).resolve().parent / "tests/exam.jpg")
print(f"扫描: {image_path}")
print("=" * 60)

result = scan_answer_sheet(image_path, REAL_SHEET_COORDINATES)

print(f"\n成功: {result['success']}")
print(f"考号: '{result['exam_number']}'")
print(f"耗时: {result['duration_ms']}ms")
print(f"总题数: {result['total_questions']}")
print(f"有效答案: {result['valid_answers']}")

print("\n" + "=" * 60)
print("逐题对比:")
print("-" * 45)
correct = 0
total = 0

for ans in result['answers']:
    qn = ans['question_number']
    got = ans['student_answer']
    expected = EXPECTED.get(qn, "")
    match = (got == expected) or (got == "" and expected == "")
    status = "OK" if match else "X"
    if match:
        correct += 1
    total += 1

    # 显示详情
    ratios = ans.get('all_ratios', {})
    ratio_str = " ".join(f"{k}:{ratios.get(k, 0):.3f}" for k in sorted(ratios.keys())[:7])
    print(f"  Q{qn:2d}: got={got or '-'} exp={expected or '-'} conf={ans['confidence']:.3f} [{status}]")
    print(f"       {ratio_str}")

print("-" * 45)
print(f"\n准确率: {correct}/{total} = {correct/total*100:.1f}%")
