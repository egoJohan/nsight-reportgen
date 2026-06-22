"""Tests for DataHiveClient stub interface."""
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
    """Test that each DataHiveClient method raises NotImplementedError."""

    def setUp(self):
        self.client = DataHiveClient(base_url="http://test", token="test_token")

    def test_create_case_raises_not_implemented(self):
        """create_case raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.client.create_case(name="test_case")

    def test_list_cases_raises_not_implemented(self):
        """list_cases raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.client.list_cases()

    def test_attach_material_raises_not_implemented(self):
        """attach_material raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.client.attach_material(
                case_id="case_1",
                name="material_1",
                sav_bytes=b"test",
                codebook_summary="summary"
            )

    def test_save_report_raises_not_implemented(self):
        """save_report raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.client.save_report(
                case_id="case_1",
                report_id=None,
                report_json='{"test": "json"}',
                readable="readable"
            )

    def test_load_report_raises_not_implemented(self):
        """load_report raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.client.load_report(report_doc_id="report_1")

    def test_aggregate_raises_not_implemented(self):
        """aggregate raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.client.aggregate(
                material_id="material_1",
                group_by=["field1"],
                filters={"key": "value"},
                weight=None
            )


class TestDataHiveClientMockability(unittest.TestCase):
    """Test that DataHiveClient is mockable with spec."""

    def test_magic_mock_spec_has_all_methods(self):
        """MagicMock(spec=DataHiveClient) has all 6 methods."""
        mock = MagicMock(spec=DataHiveClient)

        # Verify all methods are present in the spec
        self.assertTrue(hasattr(mock, "create_case"))
        self.assertTrue(hasattr(mock, "list_cases"))
        self.assertTrue(hasattr(mock, "attach_material"))
        self.assertTrue(hasattr(mock, "save_report"))
        self.assertTrue(hasattr(mock, "load_report"))
        self.assertTrue(hasattr(mock, "aggregate"))

        # Verify we can call them without errors (they are mocks)
        mock.create_case(name="test")
        mock.list_cases()
        mock.attach_material(case_id="1", name="m", sav_bytes=b"x", codebook_summary="s")
        mock.save_report(case_id="1", report_id=None, report_json="{}", readable="r")
        mock.load_report(report_doc_id="1")
        mock.aggregate(material_id="1", group_by=[], filters={})


if __name__ == "__main__":
    unittest.main()
