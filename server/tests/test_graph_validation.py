import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import mysql
from app.api.v1 import knowledge_graph
from app.api.deps import get_current_teacher_id
from app.db.database import get_db
from pydantic import ValidationError
from app.schemas.knowledge_graph import KGUpdateRequest, KGGenerateRequest
from app.services.knowledge_graph_service import KnowledgeGraphService


class GraphValidationTests(unittest.TestCase):
    def test_duplicate_ids_across_sections_cannot_be_saved(self):
        sections = [
            {'id': 's1', 'title': 'A', 'children': [{'id': 'n1', 'title': 'One'}]},
            {'id': 's2', 'title': 'B', 'children': [{'id': 'n1', 'title': 'Two'}]},
        ]
        with self.assertRaises(ValidationError):
            KGUpdateRequest(content=sections)

    def test_blank_titles_and_invalid_generation_counts_are_rejected(self):
        with self.assertRaises(ValidationError):
            KGGenerateRequest(title='   ')
        with self.assertRaises(ValidationError):
            KGGenerateRequest(title='Lesson', expected_sections=0)
        with self.assertRaises(ValidationError):
            KGUpdateRequest(content=[{'id': 's1', 'title': ' ', 'children': []}])

    def test_ai_duplicate_ids_are_rejected_before_persistence(self):
        text = json.dumps({'sections': [{'id': 'same', 'title': 'Lesson', 'children': [{'id': 'same', 'title': 'Topic'}]}]})
        with self.assertRaises(ValueError):
            KnowledgeGraphService._parse_kg_json(text)

    def test_ai_missing_ids_are_generated_and_valid(self):
        sections = KnowledgeGraphService._parse_kg_json(json.dumps({'sections': [{'title': 'Lesson', 'children': [{'title': 'Topic'}]}]}))
        model = KGUpdateRequest(content=sections)
        self.assertNotEqual(model.content[0].id, model.content[0].children[0].id)

    def test_malformed_ai_children_raise_validation_error(self):
        for children in ({'id': 'n'}, ['invalid']):
            with self.subTest(children=children), self.assertRaises(ValueError):
                KnowledgeGraphService._parse_kg_json(json.dumps({
                    'sections': [{'title': 'Lesson', 'children': children}]}))


class GraphConfirmTests(unittest.IsolatedAsyncioTestCase):
    def database(self, graph):
        return SimpleNamespace(execute=AsyncMock(return_value=Mock(
            scalar_one_or_none=Mock(return_value=graph))), commit=AsyncMock(), refresh=AsyncMock())

    async def test_empty_graph_cannot_be_confirmed(self):
        graph = SimpleNamespace(id=1, status='draft', content={'sections': []})
        db = SimpleNamespace(execute=AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=graph))), commit=AsyncMock(), refresh=AsyncMock())
        with self.assertRaises(ValueError):
            await KnowledgeGraphService.confirm_graph(db, 1, 2)
        self.assertEqual(graph.status, 'draft')
        db.commit.assert_not_awaited()

    async def test_valid_confirmation_is_idempotent_and_locks_owner_row(self):
        graph = SimpleNamespace(id=1, status='draft', content={'sections': [
            {'id': 's', 'title': 'Lesson', 'children': [{'id': 'n', 'title': 'Topic'}]}]})
        db = self.database(graph)
        self.assertEqual((await KnowledgeGraphService.confirm_graph(db, 1, 2))['status'], 'confirmed')
        await KnowledgeGraphService.confirm_graph(db, 1, 2)
        db.commit.assert_awaited_once()
        sql = str(db.execute.call_args.args[0].compile(dialect=mysql.dialect()))
        self.assertIn('FOR UPDATE', sql)
        self.assertIn('teacher_id', sql)

    async def test_confirmed_graph_rejects_edit_without_commit(self):
        db = self.database(SimpleNamespace(status='confirmed'))
        with self.assertRaises(ValueError):
            await KnowledgeGraphService.update_graph(db, 1, 2, [])
        db.commit.assert_not_awaited()

    async def test_valid_edit_normalizes_title_and_persists_tree(self):
        graph = SimpleNamespace(status='draft')
        db = self.database(graph)
        with patch.object(KnowledgeGraphService, 'get_graph', AsyncMock(return_value={'id': 1})):
            await KnowledgeGraphService.update_graph(db, 1, 2, [
                {'id': 's', 'title': 'Lesson', 'children': []}], ' Lesson ')
        self.assertEqual(graph.title, 'Lesson')
        self.assertEqual(graph.content['sections'][0]['id'], 's')
        db.commit.assert_awaited_once()


class GraphHTTPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(knowledge_graph.router, prefix='/api/v1')
        self.db = SimpleNamespace(execute=AsyncMock(return_value=Mock(
            scalar_one_or_none=Mock(return_value=SimpleNamespace(
                id=1, status='draft', content={'sections': []})))), commit=AsyncMock())

        async def database():
            yield self.db

        self.app.dependency_overrides[get_db] = database
        self.app.dependency_overrides[get_current_teacher_id] = lambda: 2
        self.path = '/api/v1/teacher/ppt/knowledge-graph/1'

    async def test_duplicate_edit_returns_422_before_database_access(self):
        async with AsyncClient(transport=ASGITransport(app=self.app), base_url='http://test') as client:
            response = await client.put(self.path, json={'content': [
                {'id': 'same', 'title': 'Lesson', 'children': [{'id': 'same', 'title': 'Topic'}]}]})
        self.assertEqual(response.status_code, 422)
        self.db.execute.assert_not_awaited()

    async def test_empty_confirmation_returns_400_without_commit(self):
        async with AsyncClient(transport=ASGITransport(app=self.app), base_url='http://test') as client:
            response = await client.post(self.path + '/confirm')
        self.assertEqual(response.status_code, 400)
        self.assertIn('知识点', response.json()['detail'])
        self.db.commit.assert_not_awaited()

    async def test_missing_or_foreign_graph_returns_404(self):
        self.db.execute.return_value.scalar_one_or_none.return_value = None
        async with AsyncClient(transport=ASGITransport(app=self.app), base_url='http://test') as client:
            response = await client.post(self.path + '/confirm')
        self.assertEqual(response.status_code, 404)
        self.db.commit.assert_not_awaited()
