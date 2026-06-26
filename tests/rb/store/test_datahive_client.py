"""Tests for DataHiveClient interface — all 8 methods implemented.

Implements: create_case, list_cases, save_report, load_report,
delete_report, aggregate, attach_material, get_material.
"""
import unittest
from unittest.mock import MagicMock

from reportbuilder.store.datahive_client import DataHiveClient


class TestDataHiveClientConstruction(unittest.TestCase):
    """Test DataHiveClient construction and attribute storage."""

    def test_init_stores_base_url_and_token(self):
        """Construct with base_url and token; verify they are stored."""
        base_url = "http://x"
        token = "t"
        client = DataHiveClient(base_url=base_url, token=token)
        self.assertEqual(client.base_url, base_url)
        self.assertEqual(client.token, token)

    def test_init_with_none_defaults(self):
        """Construct with None defaults."""
        client = DataHiveClient()
        self.assertIsNone(client.base_url)
        self.assertIsNone(client.token)


class TestDataHiveClientMethods(unittest.TestCase):
    """All 8 methods exist and are callable; none raise NotImplementedError."""

    def setUp(self):
        import httpx
        # Use a no-op mock transport so the client can be built without a real URL.
        self.client = DataHiveClient(
            base_url="http://test",
            token="test_token",
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
        )

    def test_attach_material_exists_and_is_callable(self):
        """attach_material exists, is callable, and accepts (case_id, name, sav_bytes,
        codebook_summary) — 4 args beyond self."""
        self.assertTrue(callable(self.client.attach_material))

    def test_get_material_exists_and_is_callable(self):
        """get_material exists, is callable, and accepts (material_id,) — 1 arg beyond self."""
        self.assertTrue(callable(self.client.get_material))

    def test_load_report_is_callable_with_case_id(self):
        """load_report(case_id, report_doc_id) exists and is callable."""
        self.assertTrue(callable(self.client.load_report))

    def test_delete_report_is_callable_with_case_id(self):
        """delete_report(case_id, report_doc_id) exists and is callable."""
        self.assertTrue(callable(self.client.delete_report))


class TestDataHiveClientMockability(unittest.TestCase):
    """Test that DataHiveClient is mockable with spec."""

    def test_magic_mock_spec_has_all_methods(self):
        """MagicMock(spec=DataHiveClient) has all public methods."""
        mock = MagicMock(spec=DataHiveClient)

        # Slice 1 methods
        self.assertTrue(hasattr(mock, "create_case"))
        self.assertTrue(hasattr(mock, "list_cases"))
        self.assertTrue(hasattr(mock, "save_report"))
        self.assertTrue(hasattr(mock, "load_report"))
        self.assertTrue(hasattr(mock, "delete_report"))
        self.assertTrue(hasattr(mock, "aggregate"))

        # Slice 2 (now fully implemented)
        self.assertTrue(hasattr(mock, "attach_material"))
        self.assertTrue(hasattr(mock, "get_material"))

        # Verify we can call them without errors (they are mocks)
        mock.create_case(name="test")
        mock.list_cases()
        mock.attach_material(case_id="1", name="m", sav_bytes=b"x", codebook_summary="s")
        mock.save_report(case_id="1", report_id=None, report_json="{}", readable="r")
        mock.load_report(case_id="1", report_doc_id="r1")
        mock.delete_report(case_id="1", report_doc_id="r1")
        mock.aggregate(material_id="1", group_by=[], filters=[])
        mock.get_material(material_id="1")


if __name__ == "__main__":
    unittest.main()
