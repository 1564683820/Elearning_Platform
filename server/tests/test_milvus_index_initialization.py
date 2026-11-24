import unittest
from unittest.mock import Mock, patch

from app.services.embedding_service import EmbeddingService


class MilvusIndexInitializationTests(unittest.TestCase):
    def setUp(self):
        definitions = {'test_docs': {'indexes': [
            {'field': 'embedding', 'index_type': 'FLAT', 'metric_type': 'IP'},
            {'field': 'sparse_embedding', 'index_type': 'SPARSE_INVERTED_INDEX', 'metric_type': 'IP'},
        ]}}
        self.enterContext(patch.object(EmbeddingService, '_get_collection_defs', return_value=definitions))
        self.client = Mock()

    def test_existing_indexes_do_not_trigger_creation(self):
        self.client.describe_index.return_value = {'index_name': 'existing'}

        EmbeddingService._ensure_indexes(self.client, 'test_docs')

        self.client.create_index.assert_not_called()
        self.client.load_collection.assert_called_once_with('test_docs')

    def test_missing_index_is_passed_to_client_in_sdk_format(self):
        self.client.describe_index.side_effect = [{'index_name': 'embedding'}, None]

        EmbeddingService._ensure_indexes(self.client, 'test_docs')

        self.client.create_index.assert_called_once()
        request = self.client.create_index.call_args.kwargs
        self.assertEqual(request['collection_name'], 'test_docs')
        self.assertEqual([index['field_name'] for index in request['index_params']], ['sparse_embedding'])
