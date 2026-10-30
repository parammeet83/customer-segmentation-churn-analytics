"""Create least-privilege roles and the application schema.

Run once per database with an administrative connection
(``ADMIN_DATABASE_URL``). Passwords come from ``CP_MIGRATOR_PASSWORD``,
``CP_WRITER_PASSWORD`` and ``CP_READER_PASSWORD`` and are never logged.

* ``cp_migrator`` - owns schema ``customerpulse``; runs Alembic migrations.
* ``cp_writer``   - SELECT/INSERT/UPDATE/DELETE on application tables; no DDL.
* ``cp_reader``   - SELECT only, sessions default to read-only; used by the API.
"""

from __future__ import annotations

import logging
import os

import psycopg
from psycopg import sql

from customerpulse.settings import get_settings

logger = logging.getLogger(__name__)

SCHEMA = "customerpulse"
ROLES = {
    "cp_migrator": "CP_MIGRATOR_PASSWORD",
    "cp_writer": "CP_WRITER_PASSWORD",
    "cp_reader": "CP_READER_PASSWORD",
}


def _libpq_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def role_statements(dbname: str) -> list[sql.Composed]:
    s, db = sql.Identifier(SCHEMA), sql.Identifier(dbname)
    mig, wri, rea = (sql.Identifier(r) for r in ROLES)
    return [
        sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(db),
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}, {}").format(db, mig, wri, rea),
        sql.SQL("GRANT {} TO CURRENT_USER").format(mig),
        sql.SQL("CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}").format(s, mig),
        sql.SQL("ALTER SCHEMA {} OWNER TO {}").format(s, mig),
        sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(s),
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}, {}").format(s, wri, rea),
        sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO {}").format(s, wri),
        sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}").format(s, wri),
        sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(s, rea),
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
        ).format(mig, s, wri),
        sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT USAGE, SELECT ON SEQUENCES TO {}").format(
            mig, s, wri
        ),
        sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT SELECT ON TABLES TO {}").format(mig, s, rea),
        sql.SQL("ALTER ROLE {} SET search_path = {}").format(mig, s),
        sql.SQL("ALTER ROLE {} SET search_path = {}").format(wri, s),
        sql.SQL("ALTER ROLE {} SET search_path = {}").format(rea, s),
        sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(rea),
    ]


def setup_roles(admin_url: str | None = None) -> None:
    admin_url = admin_url or get_settings().admin_database_url
    if not admin_url:
        raise RuntimeError("ADMIN_DATABASE_URL is not configured")
    passwords = {}
    for role, env in ROLES.items():
        pw = os.environ.get(env, "")
        if len(pw) < 16:
            raise RuntimeError(f"{env} must be set (16+ characters)")
        passwords[role] = pw

    with psycopg.connect(_libpq_url(admin_url), autocommit=True) as conn:
        dbname = conn.info.dbname
        for role, pw in passwords.items():
            exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
            verb = "ALTER" if exists else "CREATE"
            conn.execute(
                sql.SQL(verb + " ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(pw)
                )
            )
            logger.info("%s role %s", verb.lower() + "d", role)
        for stmt in role_statements(dbname):
            conn.execute(stmt)
    logger.info("Roles and schema %s configured in database %s", SCHEMA, dbname)
