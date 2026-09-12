"""Singleton Appwrite client and service accessors.

The client is configured from application settings and cached so the whole
backend shares one instance. Service accessors are also cached; import the
accessor you need rather than building services ad hoc.
"""

import logging
from functools import lru_cache

from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.storage import Storage
from appwrite.services.teams import Teams
from appwrite.services.users import Users

from app.config import get_settings

DATABASE_ID = "nokware"
_DEPRECATION_MARKER = "has been deprecated since"


class _DropSdkDeprecations(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return _DEPRECATION_MARKER not in record.getMessage()


def quiet_sdk_deprecation_warnings() -> None:
    """Hide the SDK's per-call "Databases API is deprecated" warnings.

    The 'nokware' database is a legacy-type database, so the Databases API is
    the right one for it on this 1.9 server. The SDK forces these warnings on
    for every call (it resets warning filters itself, so warnings.filterwarnings
    cannot stop them); routing warnings through logging lets us drop just these
    while every other warning still shows.
    """
    logging.captureWarnings(True)
    logging.getLogger("py.warnings").addFilter(_DropSdkDeprecations())


@lru_cache
def get_client() -> Client:
    settings = get_settings()
    client = Client()
    client.set_endpoint(settings.appwrite_endpoint)
    client.set_project(settings.appwrite_project_id)
    client.set_key(settings.appwrite_api_key)
    return client


@lru_cache
def get_databases() -> Databases:
    return Databases(get_client())


@lru_cache
def get_teams() -> Teams:
    return Teams(get_client())


@lru_cache
def get_users() -> Users:
    return Users(get_client())


@lru_cache
def get_storage() -> Storage:
    return Storage(get_client())
