"""Database access layer for SL Legal Assist."""

from .ids import new_id
from .repositories import LegalWorkspaceRepository
from .session import database_health, make_engine, session_scope

__all__ = [
    "LegalWorkspaceRepository",
    "database_health",
    "make_engine",
    "new_id",
    "session_scope",
]
