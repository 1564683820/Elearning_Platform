"""
教材数据初始化脚本

为 Phase 4 教材点读初始化人教版 PEP 三~六年级教材结构数据。
包括: 单元(TextbookUnit)、页面占位(TextbookPage)。

用法:
  python -m scripts.init_textbook [--version PEP] [--grade 3] [--dry-run]

数据来源: 人教版 PEP（三年级起点）教材目录
每人教(PEP)年级包含: 上下两册，每册约 6 个单元 + 2 个复习单元
"""
import asyncio
import argparse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import async_session
from app.models.textbook_models import TextbookUnit, TextbookPage


# ========== PEP 教材目录数据 ==========

PEP_UNITS = {
    "3": {
        "上": [
            ("Unit1", "Hello!", "Hello"),
            ("Unit2", "Colours", "Colors"),
            ("Unit3", "Look at me!", "Body"),
            ("Recycle1", "复习1", ""),
            ("Unit4", "We love animals", "Animals"),
            ("Unit5", "Let's eat!", "Food"),
            ("Unit6", "Happy birthday!", "Numbers"),
            ("Recycle2", "复习2", ""),
        ],
        "下": [
            ("Unit1", "Welcome back to school", "Welcome"),
            ("Unit2", "My family", "Family"),
            ("Unit3", "At the zoo", "Zoo"),
            ("Recycle1", "复习1", ""),
            ("Unit4", "Where is my car?", "Position"),
            ("Unit5", "Do you like pears?", "Fruit"),
            ("Unit6", "How many?", "Numbers"),
            ("Recycle2", "复习2", ""),
        ],
    },
    "4": {
        "上": [
            ("Unit1", "My classroom", "Classroom"),
            ("Unit2", "My schoolbag", "Schoolbag"),
            ("Unit3", "My friends", "Friends"),
            ("Recycle1", "复习1", ""),
            ("Unit4", "My home", "Home"),
            ("Unit5", "Dinner's ready", "Food"),
            ("Unit6", "Meet my family!", "Family"),
            ("Recycle2", "复习2", ""),
        ],
        "下": [
            ("Unit1", "My school", "School"),
            ("Unit2", "What time is it?", "Time"),
            ("Unit3", "Weather", "Weather"),
            ("Recycle1", "复习1", ""),
            ("Unit4", "At the farm", "Farm"),
            ("Unit5", "My clothes", "Clothes"),
            ("Unit6", "Shopping", "Shopping"),
            ("Recycle2", "复习2", ""),
        ],
    },
    "5": {
        "上": [
            ("Unit1", "What's he like?", "Teacher"),
            ("Unit2", "My week", "Week"),
            ("Unit3", "What would you like?", "Food"),
            ("Recycle1", "复习1", ""),
            ("Unit4", "What can you do?", "Ability"),
            ("Unit5", "There is a big bed", "Room"),
            ("Unit6", "In a nature park", "Nature"),
            ("Recycle2", "复习2", ""),
        ],
        "下": [
            ("Unit1", "My day", "Daily"),
            ("Unit2", "My favourite season", "Season"),
            ("Unit3", "My school calendar", "Calendar"),
            ("Recycle1", "复习1", ""),
            ("Unit4", "When is the art show?", "Date"),
            ("Unit5", "Whose dog is it?", "Possession"),
            ("Unit6", "Work quietly!", "Rules"),
            ("Recycle2", "复习2", ""),
        ],
    },
    "6": {
        "上": [
            ("Unit1", "How can I get there?", "Direction"),
            ("Unit2", "Ways to go to school", "Transport"),
            ("Unit3", "My weekend plan", "Plan"),
            ("Recycle1", "复习1", ""),
            ("Unit4", "I have a pen pal", "Hobby"),
            ("Unit5", "What does he do?", "Job"),
            ("Unit6", "How do you feel?", "Feeling"),
            ("Recycle2", "复习2", ""),
        ],
        "下": [
            ("Unit1", "How tall are you?", "Comparison"),
            ("Unit2", "Last weekend", "Past"),
            ("Unit3", "Where did you go?", "Trip"),
            ("Recycle1", "复习1", ""),
            ("Unit4", "Then and now", "Change"),
            ("Recycle2", "复习2", ""),
        ],
    },
}

# 每单元的典型页码范围
UNIT_PAGE_RANGES = {
    "Unit1": (2, 11), "Unit2": (12, 21), "Unit3": (22, 31),
    "Unit4": (32, 41), "Unit5": (42, 51), "Unit6": (52, 61),
    "Recycle1": (62, 67), "Recycle2": (68, 73),
}

PAGES_PER_UNIT = 10  # 缺省每单元页数


async def init_textbook(
    version: str = "PEP",
    grade: str = "3",
    semester: str = "",
    dry_run: bool = False,
):
    """
    初始化指定教材的数据

    Args:
        version: 教材版本
        grade: 年级（空=全部）
        semester: 学期（空=全部）
        dry_run: 仅打印，不写入数据库
    """
    async with async_session() as db:
        grades_to_init = [grade] if grade else PEP_UNITS.keys()
        for g in grades_to_init:
            if g not in PEP_UNITS:
                print(f"⚠️ 年级 {g} 无预定义数据，跳过")
                continue

            semesters_to_init = [semester] if semester else PEP_UNITS[g].keys()
            for sem in semesters_to_init:
                if sem not in PEP_UNITS[g]:
                    print(f"⚠️ {g}年级{sem}学期无预定义数据，跳过")
                    continue

                units = PEP_UNITS[g][sem]
                for sort_idx, (unit_num, title, sub_title) in enumerate(units):
                    page_start, page_end = UNIT_PAGE_RANGES.get(unit_num, (1, PAGES_PER_UNIT))

                    print(f"  [{g}·{sem}] {unit_num}: {title} (page {page_start}-{page_end})")

                    if not dry_run:
                        # 创建/更新单元
                        stmt = await db.execute(
                            __import__("sqlalchemy").select(TextbookUnit).where(
                                __import__("sqlalchemy").and_(
                                    TextbookUnit.textbook_version == version,
                                    TextbookUnit.grade == g,
                                    TextbookUnit.semester == sem,
                                    TextbookUnit.unit_number == unit_num,
                                )
                            )
                        )
                        existing_unit = stmt.scalar_one_or_none()

                        if existing_unit:
                            unit = existing_unit
                            unit.title = title
                            unit.sub_title = sub_title
                            unit.sort_order = sort_idx
                            unit.page_start = page_start
                            unit.page_end = page_end
                        else:
                            unit = TextbookUnit(
                                textbook_version=version,
                                grade=g,
                                semester=sem,
                                unit_number=unit_num,
                                title=title,
                                sub_title=sub_title,
                                sort_order=sort_idx,
                                page_start=page_start,
                                page_end=page_end,
                            )
                            db.add(unit)

                        await db.flush()

                        # 创建页面占位
                        for pn in range(page_start, page_end + 1):
                            s_page = await db.execute(
                                __import__("sqlalchemy").select(TextbookPage).where(
                                    __import__("sqlalchemy").and_(
                                        TextbookPage.textbook_version == version,
                                        TextbookPage.grade == g,
                                        TextbookPage.semester == sem,
                                        TextbookPage.unit_number == unit_num,
                                        TextbookPage.page_number == pn,
                                    )
                                )
                            )
                            if not s_page.scalar_one_or_none():
                                page = TextbookPage(
                                    unit_id=unit.id,
                                    textbook_version=version,
                                    grade=g,
                                    semester=sem,
                                    unit_number=unit_num,
                                    page_number=pn,
                                    text_content=f"{title} - Page {pn}",
                                    sentences_json=[],
                                    words_json=[],
                                    is_active=1,
                                )
                                db.add(page)

        if not dry_run:
            await db.commit()
            print(f"\n✅ 教材数据初始化完成! 版本={version}, 年级={grade}, 学期={semester}")


def main():
    """CLI 入口"""
    parser = argparse.ArgumentParser(description="教材数据初始化脚本")
    parser.add_argument("--version", default="PEP", help="教材版本")
    parser.add_argument("--grade", default="", help="年级（空=全部）")
    parser.add_argument("--semester", default="", help="学期（空=全部）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印不写入")

    args = parser.parse_args()

    print(f"教材数据初始化: version={args.version}")
    asyncio.run(init_textbook(
        version=args.version,
        grade=args.grade,
        semester=args.semester,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
