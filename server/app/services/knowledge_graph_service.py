"""知识图谱生成与 CRUD 服务

两阶段流程：
第一阶段：教师输入课程内容，AI 生成结构化的知识图谱（章节→知识点树）
第二阶段：教师确认图谱后，AI 基于图谱为每个知识点生成 PPT 幻灯片

SSE 进度约定（generate_graph_stream yield 的 dict）：
- {"type": "progress", "progress": 0~90, "message": "..."} — 中间进度
- {"type": "error", "message": "..."} — 出错终止
- {"type": "complete", "progress": 100, "data": {...}} — 成功结束
"""
import json
import logging
import re
import uuid
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.services.ai_service import AIService
from agent.agents.ppt_agent import PPTAgent, KG_GENERATE_SYSTEM_PROMPT, PPT_FROM_KG_USER_PROMPT_TEMPLATE, LESSON_TYPE_NAMES
from app.models.knowledge_graph import KnowledgeGraph
from app.schemas.knowledge_graph import KGUpdateRequest
from app.models.ppt_models import LessonPPT
from app.services.ppt_theme_service import PPTThemeService
from app.services.ppt_html_renderer import PPTHtmlRenderer

logger = logging.getLogger("knowledge_graph")


class KnowledgeGraphService:
    """知识图谱服务：生成、CRUD、确认锁定、图谱→PPT 生成"""

    @staticmethod
    def _get_lesson_type_name(lesson_type: str) -> str:
        """获取课型中文名称"""
        names = {
            "new_lesson": "新授课",
            "review": "复习课",
            "exercise": "练习课",
            "conversation": "口语课",
        }
        return names.get(lesson_type, lesson_type)

    @staticmethod
    def _generate_node_id(prefix: str = "node") -> str:
        """生成唯一点节点 ID"""
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _generate_section_id() -> str:
        """生成唯一点章节 ID"""
        return KnowledgeGraphService._generate_node_id("sec")

    @staticmethod
    def _parse_kg_json(text: str) -> list:
        """解析 AI 返回的知识图谱 JSON，返回 sections 列表

        从回复中提取 JSON，解析 {sections: [...]} 结构，
        为每个 section 和 node 补充缺失的 id 字段。
        """
        # 提取 JSON 对象
        json_match = re.search(r'\{[\s\S]*\}', text)
        if not json_match:
            raise ValueError("AI 返回内容不包含合法 JSON")

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            # 尝试去除 markdown 代码块标记后重试
            cleaned = re.sub(r'^```(?:json)?\s*', '', text)
            cleaned = re.sub(r'\s*```$', '', cleaned)
            json_match = re.search(r'\{[\s\S]*\}', cleaned)
            if not json_match:
                raise ValueError("AI 返回 JSON 解析失败")
            data = json.loads(json_match.group())

        sections = data.get("sections", [])
        if not isinstance(sections, list) or not sections:
            raise ValueError("AI 返回的 sections 为空或格式错误")

        validated = []
        for sec in sections:
            if not isinstance(sec, dict) or not isinstance(sec.get("children", []), list):
                raise ValueError("AI 返回章节结构错误")
            children = []
            for child in sec.get("children", []):
                if not isinstance(child, dict):
                    raise ValueError("AI 返回知识点结构错误")
                children.append({
                    "id": child.get("id") or KnowledgeGraphService._generate_node_id(),
                    "title": child.get("title", ""),
                    "description": child.get("description", ""),
                    "order": child.get("order", len(children) + 1),
                    "suggested_page_type": child.get("suggested_page_type", ""),
                })
            validated.append({
                "id": sec.get("id") or KnowledgeGraphService._generate_section_id(),
                "title": sec.get("title", ""),
                "order": sec.get("order", len(validated) + 1),
                "children": children,
            })

        return KGUpdateRequest(content=validated).model_dump()["content"]

    # ========== 第一阶段：生成知识图谱 ==========

    @staticmethod
    async def generate_graph(
        db: AsyncSession,
        teacher_id: int,
        title: str,
        lesson_type: str,
        subject: str = "",
        grade: str = "",
        supplement: str = "",
        expected_sections: int = 4,
        expected_nodes_per_section: int = 3,
    ) -> dict:
        """AI 生成知识图谱，保存到数据库"""

        type_name = KnowledgeGraphService._get_lesson_type_name(lesson_type)

        # 构造用户 Prompt
        user_prompt = f"""请为以下课程设计知识图谱：

课程标题: {title}
课型: {type_name}
主题: {subject or title}
年级: {grade or '未指定'}
{"补充说明: " + supplement if supplement else ""}

期望章节数: {expected_sections} 个章节
期望每章节知识点数: {expected_nodes_per_section} 个知识点"""

        try:
            result_text = await AIService.chat_completion(
                db=db,
                messages=[
                    {"role": "system", "content": KG_GENERATE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                user_id=teacher_id,
                key_type="llm",
            )
        except Exception as e:
            raise ValueError(f"AI 生成知识图谱失败: {str(e)}")

        # 解析 AI 返回的 JSON
        sections = KnowledgeGraphService._parse_kg_json(result_text)

        # 保存到数据库
        kg = KnowledgeGraph(
            ppt_id=None,
            teacher_id=teacher_id,
            title=title,
            lesson_type=lesson_type,
            subject=subject,
            grade=grade,
            content={"sections": sections},
            status="draft",
        )
        db.add(kg)
        await db.commit()
        await db.refresh(kg)

        return {
            "id": kg.id,
            "title": kg.title,
            "content": kg.content,
            "status": kg.status,
        }

    # ========== SSE 流式生成 ==========

    @staticmethod
    async def generate_graph_stream(
        teacher_id: int,
        title: str,
        lesson_type: str,
        subject: str = "",
        grade: str = "",
        supplement: str = "",
        expected_sections: int = 4,
        expected_nodes_per_section: int = 3,
        api_config: tuple[str, str, str] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """SSE 流式生成知识图谱，通过 yield 输出进度事件

        优化：不持有 DB 参数，LLM 调用期间不占用数据库连接。
        仅在需要读写数据库时创建短暂的 DB 会话。
        api_config 为预获取的 (api_key, api_base, model) 元组。
        """
        from app.db.database import async_session as _get_async_session

        type_name = KnowledgeGraphService._get_lesson_type_name(lesson_type)

        # Step 1
        print("[KG Service] Step 1: 准备请求", flush=True)
        yield {"type": "progress", "progress": 5, "message": "正在准备请求..."}

        user_prompt = f"""请为以下课程设计知识图谱：

课程标题: {title}
课型: {type_name}
主题: {subject or title}
年级: {grade or '未指定'}
{"补充说明: " + supplement if supplement else ""}

期望章节数: {expected_sections} 个章节
期望每章节知识点数: {expected_nodes_per_section} 个知识点"""

        # Step 2 — 请求 AI（不持有 DB 连接）
        print("[KG Service] Step 2: 开始 AI 请求", flush=True)
        yield {"type": "progress", "progress": 10, "message": "正在向 AI 发送请求..."}

        try:
            yield {"type": "progress", "progress": 15, "message": "AI 正在分析课程内容，请稍候..."}
            print("[KG Service] 调用 AIService.chat_completion...", flush=True)
            import time
            t0 = time.time()
            result_text = await AIService.chat_completion(
                db=None,  # 无 DB 连接，使用预获取配置
                messages=[
                    {"role": "system", "content": KG_GENERATE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                user_id=teacher_id,
                key_type="llm",
                api_config=api_config,  # 使用预获取的配置
            )
            elapsed = time.time() - t0
            print(f"[KG Service] AI 调用完成 | 耗时={elapsed:.1f}s | 返回长度={len(result_text)}", flush=True)
        except Exception as e:
            print(f"[KG Service] AI 调用异常: {e}", flush=True)
            yield {"type": "error", "message": f"AI 生成知识图谱失败: {str(e)}"}
            return

        # Step 3 — 解析
        yield {"type": "progress", "progress": 70, "message": "正在解析 AI 返回结果..."}

        try:
            sections = KnowledgeGraphService._parse_kg_json(result_text)
        except ValueError as e:
            yield {"type": "error", "message": str(e)}
            return

        # Step 4 — 保存（短暂打开 DB 会话）
        yield {"type": "progress", "progress": 85, "message": "正在保存知识图谱..."}

        async with _get_async_session() as db:
            kg = KnowledgeGraph(
                ppt_id=None,
                teacher_id=teacher_id,
                title=title,
                lesson_type=lesson_type,
                subject=subject,
                grade=grade,
                content={"sections": sections},
                status="draft",
            )
            db.add(kg)
            await db.commit()
            # 不调用 refresh，避免触发隐式 autobegin 事务
            # commit 后即可读取 kg.id（已由数据库自增/Snowflake 填充）

            logger.info(
                "SSE 知识图谱保存成功 | kg_id=%s teacher_id=%s title=%s",
                kg.id, teacher_id, title,
            )

            # 完成
            yield {
                "type": "complete",
                "progress": 100,
                "message": "知识图谱生成完成",
                "data": {
                    "id": kg.id,
                    "title": kg.title,
                    "content": kg.content,
                    "status": kg.status,
                },
            }
            # db session 自动 close()，连接归还连接池

    # ========== CRUD 操作 ==========

    @staticmethod
    async def get_graph(db: AsyncSession, kg_id: int, teacher_id: int) -> dict | None:
        """获取单个知识图谱详情"""
        result = await db.execute(
            select(KnowledgeGraph).where(
                KnowledgeGraph.id == kg_id,
                KnowledgeGraph.teacher_id == teacher_id,
            )
        )
        kg = result.scalar_one_or_none()
        if not kg:
            return None

        return {
            "id": kg.id,
            "ppt_id": kg.ppt_id,
            "teacher_id": kg.teacher_id,
            "title": kg.title,
            "lesson_type": kg.lesson_type,
            "subject": kg.subject,
            "grade": kg.grade,
            "content": kg.content,
            "status": kg.status,
            "created_at": kg.created_at.isoformat() if kg.created_at else "",
            "updated_at": kg.updated_at.isoformat() if kg.updated_at else "",
        }

    @staticmethod
    async def update_graph(
        db: AsyncSession, kg_id: int, teacher_id: int,
        content: list, title: str | None = None,
    ) -> dict | None:
        """保存知识图谱的修改（整树替换），仅在 draft 状态可修改"""
        logger.info(
            "update_graph | kg_id=%s teacher_id=%s content_len=%s title=%s",
            kg_id, teacher_id, len(content) if content else 0, title,
        )
        result = await db.execute(
            select(KnowledgeGraph).where(
                KnowledgeGraph.id == kg_id,
                KnowledgeGraph.teacher_id == teacher_id,
            ).with_for_update()
        )
        kg = result.scalar_one_or_none()
        if not kg:
            # 日志诊断：检查不按 teacher_id 过滤时是否存在
            fallback = await db.execute(
                select(KnowledgeGraph).where(KnowledgeGraph.id == kg_id)
            )
            any_kg = fallback.scalar_one_or_none()
            if any_kg:
                logger.warning(
                    "update_graph 404 | kg_id=%s 存在但 teacher_id 不匹配 | "
                    "请求 teacher_id=%s 实际 teacher_id=%s",
                    kg_id, teacher_id, any_kg.teacher_id,
                )
            else:
                logger.warning(
                    "update_graph 404 | kg_id=%s 完全不存在于 knowledge_graph 表 | "
                    "teacher_id=%s", kg_id, teacher_id,
                )
            return None
        if kg.status != "draft":
            raise ValueError("已确认的图谱不可修改，如需修改请新建")

        # 内部调用也使用与 HTTP 一致的结构验证。
        validated = KGUpdateRequest(content=content, title=title)
        kg.content = {"sections": validated.model_dump()["content"]}
        if title is not None:
            kg.title = validated.title
        await db.commit()
        await db.refresh(kg)

        return await KnowledgeGraphService.get_graph(db, kg_id, teacher_id)

    @staticmethod
    async def confirm_graph(db: AsyncSession, kg_id: int, teacher_id: int) -> dict | None:
        """确认锁定知识图谱，状态由 draft → confirmed，不可再编辑"""
        result = await db.execute(
            select(KnowledgeGraph).where(
                KnowledgeGraph.id == kg_id,
                KnowledgeGraph.teacher_id == teacher_id,
            ).with_for_update()
        )
        kg = result.scalar_one_or_none()
        if not kg:
            return None
        if kg.status == "confirmed":
            return {"id": kg.id, "status": "confirmed", "message": "图谱已确认，无需重复操作"}

        sections = (kg.content or {}).get("sections", [])
        graph = KGUpdateRequest(content=sections)
        if not graph.content or not any(section.children for section in graph.content):
            raise ValueError("图谱至少需要一个有效知识点才能确认")

        kg.status = "confirmed"
        await db.commit()
        await db.refresh(kg)

        return {"id": kg.id, "status": kg.status}

    @staticmethod
    async def list_graphs(
        db: AsyncSession, teacher_id: int,
        status: str | None = None, page: int = 1, page_size: int = 20,
    ) -> dict:
        """获取教师的知识图谱列表"""
        query = select(KnowledgeGraph).where(KnowledgeGraph.teacher_id == teacher_id)
        if status:
            query = query.where(KnowledgeGraph.status == status)
        query = query.order_by(desc(KnowledgeGraph.updated_at))

        # 总数
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        result = await db.execute(query)
        kgs = result.scalars().all()

        items = []
        for kg in kgs:
            content = kg.content or {"sections": []}
            sections = content.get("sections", [])
            node_count = sum(len(s.get("children", [])) for s in sections)
            items.append({
                "id": kg.id,
                "title": kg.title,
                "lesson_type": kg.lesson_type,
                "subject": kg.subject,
                "grade": kg.grade,
                "status": kg.status,
                "section_count": len(sections),
                "node_count": node_count,
                "created_at": kg.created_at.isoformat() if kg.created_at else "",
                "updated_at": kg.updated_at.isoformat() if kg.updated_at else "",
            })

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    # ========== 第二阶段：从图谱生成 PPT ==========

    @staticmethod
    async def generate_ppt_from_graph(
        db: AsyncSession, kg_id: int, teacher_id: int,
        theme_name: str = "classic",
        visual_style: str | None = None,
        spec_lock: dict | None = None,
    ) -> dict:
        """根据已确认的知识图谱生成完整 PPT

        流程：
        1. 验证图谱状态为 confirmed，提取 sections
        2. 委托 PPTAgent.generate_ppt_content() 调 AI 生成页内容
        3. 解析 AI 返回的 JSON → pages
        4. 写入 kg_node_ref 元数据追踪每个知识点→页面对应
        5. 保存到 LessonPPT 表，关联 knowledge_graph_id
        6. 根据 theme_name 渲染 HTML 并回填
        7. Phase 3.3: 应用 spec_lock 锁定设计规格
        """
        # 1. 获取知识图谱
        result = await db.execute(
            select(KnowledgeGraph).where(
                KnowledgeGraph.id == kg_id,
                KnowledgeGraph.teacher_id == teacher_id,
            )
        )
        kg = result.scalar_one_or_none()
        if not kg:
            raise ValueError("知识图谱不存在")
        if kg.status != "confirmed":
            raise ValueError("请先确认知识图谱后再生成 PPT")

        content = kg.content or {"sections": []}
        sections = content.get("sections", [])
        if not sections:
            raise ValueError("知识图谱内容为空")
        graph = KGUpdateRequest(content=sections)
        if not any(section.children for section in graph.content):
            raise ValueError("知识图谱缺少有效知识点")

        # 2. 委托 PPTAgent 调 AI 生成 PPT 页面内容
        from app.services.ppt_service import PPTService

        try:
            result_text = await PPTAgent.generate_ppt_content(
                db=db,
                teacher_id=teacher_id,
                title=kg.title,
                lesson_type=kg.lesson_type,
                subject=kg.subject or "",
                grade=kg.grade or "",
                sections=sections,
            )
        except Exception as e:
            import traceback as _tb
            _tb.print_exc()
            print(f"[KG->PPT] AI 调用失败详情: type={type(e).__name__} msg={e}", flush=True)
            raise ValueError(f"AI 生成 PPT 失败: {type(e).__name__}: {str(e)}")

        # 打印 AI 原始返回以供调试
        print(f"[KG->PPT] AI 原始返回（前 500 字符）: {str(result_text)[:500]}", flush=True)

        # 3. 解析 AI 返回的 JSON
        # 注意：这里不再使用 LESSON_TEMPLATES（那是模板式路径的固定页面类型顺序），
        # 而是用知识图谱的章节->知识点结构推导出模板。
        # 这样 _ensure_template_types 只会在图谱定义的类型范围内补齐，不会插入和谱无关的默认页。
        kg_template = [{"type": "title", "title": "封面"}]
        for sec in sections:
            for child in sec.get("children", []):
                pg_type = child.get("suggested_page_type", "practice")
                kg_template.append({
                    "type": pg_type,
                    "title": child.get("title", ""),
                })
        kg_template.append({"type": "summary", "title": "总结"})

        print(f"[KG->PPT] kg_template 结构: {json.dumps([{k: t.get(k) for k in ('type','title')} for t in kg_template], ensure_ascii=False)}", flush=True)

        pages = PPTService._parse_pages(result_text, len(kg_template), kg_template)
        pages = PPTService._ensure_template_types(pages, kg_template)

        # 4. 为每页添加 kg_node_ref 元数据：标记它来自哪个知识点（便于后续追踪映射）
        #    按 sections 中的 children 顺序循环分配（跳过首页末页，首页默认为 title，末页为 summary）
        node_refs = []
        for sec in sections:
            for child in sec.get("children", []):
                node_refs.append({
                    "section_title": sec.get("title", ""),
                    "section_order": sec.get("order", 0),
                    "node_title": child.get("title", ""),
                    "node_order": child.get("order", 0),
                })
        ref_idx = 0
        for page in pages:
            ptype = page.get("type", "")
            if ptype == "title":
                page["kg_node_ref"] = {"type": "cover", "section_title": "", "node_title": ""}
            elif ptype == "summary":
                page["kg_node_ref"] = {"type": "summary", "section_title": "", "node_title": ""}
            else:
                if ref_idx < len(node_refs):
                    page["kg_node_ref"] = {**node_refs[ref_idx], "type": "knowledge_node"}
                    ref_idx += 1
                else:
                    page["kg_node_ref"] = {"type": "extra", "section_title": "", "node_title": ""}

        # 5a. Phase 3.3: 应用 spec_lock 锁定设计规格（如提供）
        spec_lock_dict = None
        effective_layout_overrides = None
        if spec_lock or visual_style:
            from app.ppt_generator.analysis.spec_lock_manager import spec_lock_manager as slm
            design_spec = slm.build_spec(
                visual_style=visual_style or spec_lock.get("visual_style", "warm-simple"),
                color_scheme_name=spec_lock.get("color_scheme_name") if spec_lock else None,
                font_family_name=spec_lock.get("font_family_name") if spec_lock else None,
                layout_strategy=spec_lock.get("layout_strategy") if spec_lock else None,
                canvas_format=spec_lock.get("canvas_format", "ppt169") if spec_lock else "ppt169",
            )
            # 覆盖 theme_name（使后续 HTML 渲染匹配风格）
            from app.services.ppt_service import PPTService as PPTServiceClass
            locked_style = design_spec.visual_style
            theme_name = spec_lock.get("theme_name") if spec_lock and "theme_name" in spec_lock else PPTServiceClass._style_to_theme(locked_style)
            # 应用布局策略到页面
            layout_overrides = design_spec.layout_strategy.to_overrides()
            if layout_overrides:
                effective_layout_overrides = layout_overrides
                for p in pages:
                    ptype = p.get("type", "")
                    if ptype in layout_overrides:
                        if "content" not in p or not isinstance(p.get("content"), dict):
                            p["content"] = {}
                        p["content"]["_layout"] = layout_overrides[ptype]
            # 保存完整 spec_lock
            spec_lock_dict = design_spec.to_dict()
            if spec_lock:
                for k in ("visual_style", "color_scheme_name", "font_family_name", "canvas_format"):
                    if k in spec_lock:
                        spec_lock_dict[k] = spec_lock[k]

        # 5. 合成 PPT 内音频（listening/speaking 页）
        try:
            pages = await PPTService._synthesize_ppt_audio(pages, theme_name)
        except Exception as audio_err:
            print(f"[KG->PPT] TTS 合成失败（不影响 PPT 生成）: {audio_err}", flush=True)

        # 6. 生成大纲
        outline = [
            {"index": i, "title": p.get("title", f"第{i+1}页"),
             "slide_type": p.get("type", "practice"),
             "description": p.get("kg_node_ref", {}).get("node_title", "")}
            for i, p in enumerate(pages)
        ]

        # 7. 保存到数据库（含 spec_lock Phase 3.3）
        spec_lock_dict = locals().get("spec_lock_dict")
        ppt = LessonPPT(
            teacher_id=teacher_id,
            class_id=None,
            title=kg.title,
            lesson_type=kg.lesson_type,
            subject=kg.subject,
            grade=kg.grade,
            knowledge_graph_id=kg.id,
            outline=outline,
            pages_json=pages,
            slide_count=len(pages),
            theme_name=theme_name,
            spec_lock=spec_lock_dict,
            status="draft",
        )
        db.add(ppt)
        await db.commit()
        await db.refresh(ppt)

        # 8. 回填知识图谱的 ppt_id
        kg.ppt_id = ppt.id
        await db.commit()

        # 9. 根据主题渲染 HTML
        transition_type = "slide"
        transition_duration = 400
        try:
            theme = await PPTThemeService.get_theme_by_name(db, theme_name)
            theme_css = theme["css_content"] if theme else ""
            theme_vars = theme.get("css_variables", "") if theme else ""
            style_skill = theme.get("style_skill") if theme else None
            if style_skill and isinstance(style_skill, dict):
                anim_cfg = style_skill.get("recommended_animations", {})
                if isinstance(anim_cfg, dict):
                    transition_type = anim_cfg.get("transition", transition_type)
                    transition_duration = anim_cfg.get("duration", transition_duration)
            # Phase 3.5: 从 spec_lock_dict 提取 visual_style
            vs = ""
            sd = locals().get("spec_lock_dict")
            if sd and isinstance(sd, dict):
                vs = sd.get("visual_style", "")
            html_content = PPTHtmlRenderer.render_html_from_pages(
                pages=pages,
                title=kg.title,
                theme_css=theme_css,
                theme_name=theme_name,
                css_variables=theme_vars,
                transition_type=transition_type,
                transition_duration=transition_duration,
                visual_style=vs,
            )
            ppt.html_content = html_content
            ppt.transition_type = transition_type
            ppt.transition_duration = transition_duration
            await db.commit()
        except Exception:
            pass

        return {
            "id": ppt.id,
            "title": ppt.title,
            "outline": outline,
            "pages_json": pages,
            "slide_count": len(pages),
            "theme_name": theme_name,
        }
