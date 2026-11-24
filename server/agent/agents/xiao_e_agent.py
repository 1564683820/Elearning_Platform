"""XiaoE Agent — Mini-program student-side intelligent Q&A assistant

Responsibilities:
- Intelligent Q&A (RAG-enhanced)
- Scenario dialogue generation and evaluation
- AI dialogue context management

Related services (CRUD + DB in original):
- app.services.chat_service.ChatService
- app.services.chat_service.ScenarioService
"""

import json
from sqlalchemy.ext.asyncio import AsyncSession
from agent.agents.base import BaseAgent
from app.services.ai_service import AIService
from app.services.rag_service import RAGService


SCENE_SYSTEM_PROMPT = """You are an English conversation practice partner.
Scene: {scene_desc}
User role: {user_role}

Please reply in English, keeping the conversation natural and fluent.
If the user replies in Chinese, gently guide them to use English.
Adjust language difficulty based on {level} level."""

EVALUATION_PROMPT = """Please evaluate the following English conversation, scoring from 1-5 on grammar accuracy, vocabulary appropriateness, and expression naturalness, and give improvement suggestions:

{dialogue_text}

Return in JSON format:
{{"grammar_score": 1-5, "vocabulary_score": 1-5, "fluency_score": 1-5, "overall_score": 1-5, "feedback": "Overall evaluation and suggestions"}}"""


class XiaoEAgent(BaseAgent):
    """XiaoE Q&A Agent — Student-side intelligent English learning assistant"""

    @staticmethod
    async def get_qa_response(
        db: AsyncSession,
        message: str,
        user_id: int,
        context_messages: list[dict],
        session_type: int = 0,
        scene_desc: str = "",
        user_role: str = "",
    ) -> str:
        """Get AI response for a chat message.

        Args:
            session_type: 0=general, 1=scenario dialogue, 2=intelligent Q&A (RAG)
        """
        messages = list(context_messages) if context_messages else []

        if session_type == 2:
            rag_result = await RAGService.answer_question(db, message, user_id)
            return rag_result["answer"]

        elif session_type == 1:
            if scene_desc:
                system_msg = SCENE_SYSTEM_PROMPT.format(
                    scene_desc=scene_desc,
                    user_role=user_role or "\u5b66\u751f",
                    level="intermediate",
                )
                messages.insert(0, {"role": "system", "content": system_msg})
            return await AIService.chat_completion(db, messages, user_id)

        else:
            return await AIService.chat_completion(db, messages, user_id)

    @staticmethod
    async def evaluate_dialogue(
        db: AsyncSession,
        dialogue_text: str,
        user_id: int,
    ) -> dict:
        """Evaluate a dialogue and return scores + feedback."""
        prompt = EVALUATION_PROMPT.format(dialogue_text=dialogue_text)
        messages_for_ai = [{"role": "user", "content": prompt}]
        evaluation_text = await AIService.chat_completion(db, messages_for_ai, user_id)

        try:
            evaluation = json.loads(evaluation_text.strip())
        except json.JSONDecodeError:
            evaluation = {"overall_score": 0, "feedback": evaluation_text}
        return evaluation

    async def run(self, **kwargs) -> dict:
        """Execute XiaoE agent task."""
        action = kwargs.get("action", "qa")
        if action == "qa":
            text = await self.get_qa_response(**kwargs)
            return {"answer": text}
        elif action == "evaluate":
            return await self.evaluate_dialogue(**kwargs)
        raise ValueError("Unknown action: {}".format(action))
