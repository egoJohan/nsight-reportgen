"""Dependency injection for the FastAPI app."""
from reportbuilder.store.datahive_client import DataHiveClient


def get_client() -> DataHiveClient:
    """Default dependency: a real DataHiveClient. Overridden per-app in create_app / tests.
    Returns the app-configured client."""
    return DataHiveClient()
