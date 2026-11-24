"""PPT 生成器 CLI 入口

用法:
    # 从 pages_json 生成 PPTX
    python -m app.ppt_generator.cli from-json <pages.json> -o output.pptx
    
    # 从 PDF 生成 PPTX
    python -m app.ppt_generator.cli from-pdf <input.pdf> -o output.pptx
    
    # 从 SVG 文件生成 PPTX
    python -m app.ppt_generator.cli from-svg <svg_dir> -o output.pptx
"""
import os
import sys
import json
import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("ppt_cli")


def main():
    """CLI 主入口"""
    parser = argparse.ArgumentParser(description="PPT Generator CLI")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # from-json 子命令
    json_parser = subparsers.add_parser("from-json", help="从 JSON 文件生成 PPTX")
    json_parser.add_argument("input", help="pages_json 文件路径")
    json_parser.add_argument("-o", "--output", default="", help="输出 .pptx 文件路径")
    json_parser.add_argument("--title", default="AI 课件", help="PPT 标题")
    json_parser.add_argument("--format", default="ppt169", help="画布格式")

    # from-pdf 子命令
    pdf_parser = subparsers.add_parser("from-pdf", help="从 PDF 文件生成 PPTX")
    pdf_parser.add_argument("input", help="PDF 文件路径")
    pdf_parser.add_argument("-o", "--output", default="", help="输出 .pptx 文件路径")
    pdf_parser.add_argument("--title", default="PDF 课件", help="PPT 标题")

    # from-svg 子命令
    svg_parser = subparsers.add_parser("from-svg", help="从 SVG 文件目录生成 PPTX")
    svg_parser.add_argument("input", help="SVG 文件目录")
    svg_parser.add_argument("-o", "--output", default="", help="输出 .pptx 文件路径")

    args = parser.parse_args()

    if args.command == "from-json":
        _from_json(args)
    elif args.command == "from-pdf":
        _from_pdf(args)
    elif args.command == "from-svg":
        _from_svg(args)
    else:
        parser.print_help()


def _from_json(args):
    """从 JSON 文件生成 PPTX"""
    from .services.ppt_generation_service import PPTGenerationService

    with open(args.input, "r", encoding="utf-8") as f:
        pages_data = json.load(f)

    pages = pages_data if isinstance(pages_data, list) else pages_data.get("pages", pages_data)

    output = args.output or f"output_{Path(args.input).stem}.pptx"

    service = PPTGenerationService()
    import asyncio
    result = asyncio.run(
        service.generate_from_pages_json(pages, args.title, canvas_format=args.format)
    )
    logger.info(f"PPTX 生成完成: {result['path']}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _from_pdf(args):
    """从 PDF 生成 PPTX"""
    from .services.ppt_generation_service import PPTGenerationService

    service = PPTGenerationService()
    result = service.generate_from_pdf(args.input, args.title)
    logger.info(f"PPTX 生成完成: {result['path']}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _from_svg(args):
    """从 SVG 目录生成 PPTX"""
    from .svg_to_pptx.pptx_builder import build_pptx_from_svg_files

    svg_dir = Path(args.input)
    svg_files = sorted([str(f) for f in svg_dir.glob("*.svg")])

    if not svg_files:
        logger.error(f"未找到 SVG 文件: {svg_dir}")
        sys.exit(1)

    output = args.output or "output.pptx"
    result = build_pptx_from_svg_files(svg_files, output)
    logger.info(f"PPTX 生成完成: {result}")
    print(json.dumps({"success": True, "path": result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
