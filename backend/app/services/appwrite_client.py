"""Singleton Appwrite client and service accessors.

The client is configured from application settings and cached so the whole
backend shares one instance. Service accessors are also cached; import the
accessor you need rather than building services ad hoc.
"""

from functools import lru_cache

from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.storage import Storage
from appwrite.services.teams import Teams
from appwrite.services.users import Users

from app.config import get_settings


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
