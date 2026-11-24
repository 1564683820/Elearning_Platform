import unittest
from starlette.routing import Match
from app.main import app


class RouteReachabilityTests(unittest.TestCase):
    def test_static_endpoints_are_not_shadowed_by_dynamic_ids(self):
        for target in app.routes:
            if not hasattr(target, 'methods') or '{' in target.path:
                continue
            for method in target.methods - {'HEAD', 'OPTIONS'}:
                with self.subTest(method=method, path=target.path):
                    scope = {'type': 'http', 'path': target.path, 'method': method, 'root_path': ''}
                    first = next(route for route in app.routes if route.matches(scope)[0] == Match.FULL)
                    self.assertIs(first, target, f'{method} {target.path} shadowed by {first.path}')

    def test_snowflake_detail_routes_still_accept_full_integer_ids(self):
        for prefix, name in [
            ('/api/v1/teacher/exam', 'get_exam'),
            ('/api/v1/teacher/ppt/knowledge-graph', 'get_knowledge_graph'),
        ]:
            with self.subTest(prefix=prefix):
                scope = {'type': 'http', 'path': prefix + '/9007199254740993', 'method': 'GET', 'root_path': ''}
                route = next(route for route in app.routes if route.matches(scope)[0] == Match.FULL)
                self.assertEqual(route.endpoint.__name__, name)

    def test_openapi_paths_remain_client_compatible(self):
        paths = app.openapi()['paths']
        self.assertIn('/api/v1/teacher/exam/{exam_id}', paths)
        self.assertIn('/api/v1/teacher/ppt/knowledge-graph/{kg_id}', paths)
        self.assertIn('/api/v1/favorites/{favorite_id}', paths)
