"""分析 2023 高考英语试卷 docx 结构"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
from docx import Document

filepath = r'试卷/2023年高考英语试卷（新课标Ⅰ卷）（空白卷）.docx'
doc = Document(filepath)

print('=== 文档结构分析 ===')
print(f'段落总数: {len(doc.paragraphs)}')
print(f'表格总数: {len(doc.tables)}')
print()

empty_count = 0
content_paras = 0
styles = {}
for i, para in enumerate(doc.paragraphs):
    text = para.text.strip()
    style_name = para.style.name if para.style else 'None'
    styles[style_name] = styles.get(style_name, 0) + 1
    if text:
        content_paras += 1
    else:
        empty_count += 1

print(f'有内容段落: {content_paras}, 空段落: {empty_count}')
print(f'样式分布: {dict(sorted(styles.items(), key=lambda x: -x[1]))}')

# 全文输出（有限制）
print('\n=== 全部有内容段落 ===')
for i, para in enumerate(doc.paragraphs):
    if para.text.strip():
        print(f'[{i}] #{para.style.name}# {para.text[:200]}')

# 表格
for ti, table in enumerate(doc.tables[:5]):
    print(f'\n=== 表格{ti} ({len(table.rows)}行 x {len(table.columns)}列) ===')
    for ri, row in enumerate(table.rows[:8]):
        cells = [cell.text.strip()[:80] for cell in row.cells]
        print(f'  行{ri}: {" | ".join(cells)}')
