"""Configure the test environment before app modules are imported.

Some app modules (config, database) read environment variables at import
time via pydantic-settings.  We set dummy values here so that pure unit
tests can import app code without a real Postgres instance.

SQLAlchemy 2.0 eagerly imports asyncpg when create_async_engine() is
called with a postgresql+asyncpg URL.  We inject a minimal stub into
sys.modules FIRST so that import never reaches the real asyncpg package
(which is not installed in the test environment).
"""
from __future__ import annotations

import os
import sys
import types

# ---------------------------------------------------------------------------
# 1. Stub asyncpg BEFORE any app import
# ---------------------------------------------------------------------------

def _make_asyncpg_stub() -> None:
    """Inject a minimal asyncpg stub that satisfies SQLAlchemy's dialect."""

    class _Err(Exception):
        pass

    class PostgresError(_Err):
        pass

    class InterfaceError(_Err):
        pass

    class PostgresConnectionError(InterfaceError):
        pass

    class TooManyConnectionsError(PostgresError):
        pass

    class SyntaxOrAccessError(PostgresError):
        pass

    class InsufficientPrivilegeError(SyntaxOrAccessError):
        pass

    class DuplicateTableError(PostgresError):
        pass

    class UniqueViolationError(PostgresError):
        pass

    class ForeignKeyViolationError(PostgresError):
        pass

    class NotNullViolationError(PostgresError):
        pass

    class UndefinedColumnError(PostgresError):
        pass

    class UndefinedTableError(PostgresError):
        pass

    class DataError(PostgresError):
        pass

    class LockNotAvailable(PostgresError):
        pass

    class DeadlockDetected(PostgresError):
        pass

    class CannotConnectNowError(PostgresConnectionError):
        pass

    class ConnectionRejectionError(PostgresConnectionError):
        pass

    class IdleInTransactionSessionTimeoutError(PostgresError):
        pass

    class QueryCanceledError(PostgresError):
        pass

    class InvalidTransactionStateError(PostgresError):
        pass

    class InvalidCatalogNameError(PostgresError):
        pass

    class InvalidSchemaNameError(PostgresError):
        pass

    # -- exceptions submodule ------------------------------------------------
    exc_mod = types.ModuleType("asyncpg.exceptions")
    exc_mod.PostgresError = PostgresError
    exc_mod.InterfaceError = InterfaceError
    exc_mod.PostgresConnectionError = PostgresConnectionError
    exc_mod.TooManyConnectionsError = TooManyConnectionsError
    exc_mod.SyntaxOrAccessError = SyntaxOrAccessError
    exc_mod.InsufficientPrivilegeError = InsufficientPrivilegeError
    exc_mod.DuplicateTableError = DuplicateTableError
    exc_mod.UniqueViolationError = UniqueViolationError
    exc_mod.ForeignKeyViolationError = ForeignKeyViolationError
    exc_mod.NotNullViolationError = NotNullViolationError
    exc_mod.UndefinedColumnError = UndefinedColumnError
    exc_mod.UndefinedTableError = UndefinedTableError
    exc_mod.DataError = DataError
    exc_mod.LockNotAvailable = LockNotAvailable
    exc_mod.DeadlockDetected = DeadlockDetected
    exc_mod.CannotConnectNowError = CannotConnectNowError
    exc_mod.ConnectionRejectionError = ConnectionRejectionError
    exc_mod.IdleInTransactionSessionTimeoutError = IdleInTransactionSessionTimeoutError
    exc_mod.QueryCanceledError = QueryCanceledError
    exc_mod.InvalidTransactionStateError = InvalidTransactionStateError
    exc_mod.InvalidCatalogNameError = InvalidCatalogNameError
    exc_mod.InvalidSchemaNameError = InvalidSchemaNameError

    # -- pgproto submodule (sometimes imported by asyncpg internals) ---------
    pgproto_mod = types.ModuleType("asyncpg.pgproto")
    pgproto_mod.pgproto = types.ModuleType("asyncpg.pgproto.pgproto")

    # -- main asyncpg module -------------------------------------------------
    asyncpg_mod = types.ModuleType("asyncpg")
    asyncpg_mod.__version__ = "0.0.0-stub"
    asyncpg_mod.exceptions = exc_mod

    # Mirror top-level exception references (SQLAlchemy accesses both paths)
    for name in dir(exc_mod):
        if not name.startswith("_"):
            setattr(asyncpg_mod, name, getattr(exc_mod, name))

    async def connect(*a, **kw):  # type: ignore[empty-body]
        raise NotImplementedError("asyncpg stub: no real DB in unit tests")

    async def create_pool(*a, **kw):  # type: ignore[empty-body]
        raise NotImplementedError("asyncpg stub: no real DB in unit tests")

    asyncpg_mod.connect = connect
    asyncpg_mod.create_pool = create_pool

    sys.modules["asyncpg"] = asyncpg_mod
    sys.modules["asyncpg.exceptions"] = exc_mod
    sys.modules["asyncpg.pgproto"] = pgproto_mod
    sys.modules["asyncpg.pgproto.pgproto"] = pgproto_mod.pgproto


_make_asyncpg_stub()

# ---------------------------------------------------------------------------
# 2. Default env vars so pydantic-settings can construct Settings
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "POSTGRES_USER": "test",
    "POSTGRES_PASSWORD": "test",
    "POSTGRES_DB": "test",
    "ADSBUDDY_SECRET_KEY": "test-secret-key-for-unit-tests-only",
    "ADSBUDDY_ADMIN_USERNAME": "admin",
    "ADSBUDDY_ADMIN_PASSWORD": "admin",
}
for _k, _v in _DEFAULTS.items():
    os.environ.setdefault(_k, _v)
