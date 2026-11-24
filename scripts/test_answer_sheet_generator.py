"""测试答题卡生成函数"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from app.services.answer_sheet_generator import generate_answer_sheet_html


def test_default():
    html = generate_answer_sheet_html()
    assert "</html>" in html, "缺少 </html>"
    assert "标准答题卡" in html, "标题错误"
    assert "100." in html, "100题未出现"
    assert "参考答案" in html, "缺少参考答案页"
    print(f"[默认] OK - {len(html)} chars")


def test_7_options():
    html = generate_answer_sheet_html(
        title="七选五测试",
        question_count=30,
        options=["A", "B", "C", "D", "E", "F", "G"],
        id_digits=8,
    )
    assert "7 个选项" in html or "[G]" in html, "7个选项未出现"
    assert "30." in html, "30题未出现"
    assert "第 2 页" in html
    print(f"[7选项30题] OK - {len(html)} chars")


def test_no_answer_key():
    html = generate_answer_sheet_html(show_answer_key=False, question_count=10)
    # 检查实际的参考答案内容（而非 CSS 注释中的文字）
    assert '<div class="ans-grid">' not in html, "不应出现参考答案网格"
    assert "1.</span><span class=\"ans-val\">" not in html, "不应出现答案条目"
    assert "第 1 页" in html
    print(f"[无参考答案] OK - {len(html)} chars")


def test_full_html_valid():
    """粗略验证 HTML 结构完整性"""
    import re
    html = generate_answer_sheet_html(question_count=50, options=["A", "B", "C", "D", "E"])

    # 检查基本结构
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html.rstrip()

    # 检查标签平衡
    open_tags = len(re.findall(r"<div\b", html))
    close_tags = len(re.findall(r"</div>", html))
    assert open_tags == close_tags, f"div 标签不平衡: {open_tags} 开 vs {close_tags} 关"

    print(f"[结构验证] OK - {len(html)} chars, div: {open_tags}")


if __name__ == "__main__":
    test_default()
    test_7_options()
    test_no_answer_key()
    test_full_html_valid()
    print("\n全部测试通过")
