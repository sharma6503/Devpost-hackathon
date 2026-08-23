"""BigQuery-backed username/password auth for the frontend login gate.

Accounts are admin-provisioned via `scripts/seed_bq_user.py` — there is no
public signup path. Passwords are hashed with bcrypt (salted, one-way) before
they ever reach BigQuery; nothing downstream can recover the plaintext.
"""

from __future__ import annotations

import logging
import os

import bcrypt

logger = logging.getLogger(__name__)

BQ_PROJECT = (
    os.environ.get("BQ_PROJECT")
    or os.environ.get("GOOGLE_CLOUD_PROJECT")
    or os.environ.get("GCP_PROJECT")
    or "enterprise-ai-guardian"
)
BQ_DATASET = os.environ.get("BQ_DATASET", "agent_guardian")
BQ_USERS_TABLE = os.environ.get("BQ_USERS_TABLE", "users")

_TABLE_FQN = f"`{BQ_PROJECT}.{BQ_DATASET}.{BQ_USERS_TABLE}`"

_client = None


def _get_client():
    global _client
    if _client is None:
        from google.cloud import bigquery

        _client = bigquery.Client(project=BQ_PROJECT)
    return _client


def ensure_users_table(client=None) -> None:
    """Ensure the BigQuery dataset and users table exist, creating them if not."""
    from google.cloud import bigquery
    from google.cloud.exceptions import NotFound

    if client is None:
        client = _get_client()

    dataset_ref = bigquery.DatasetReference(BQ_PROJECT, BQ_DATASET)
    try:
        client.get_dataset(dataset_ref)
    except NotFound:
        dataset = bigquery.Dataset(dataset_ref)
        client.create_dataset(dataset, exists_ok=True)

    table_ref = dataset_ref.table(BQ_USERS_TABLE)
    try:
        client.get_table(table_ref)
    except NotFound:
        schema = [
            bigquery.SchemaField("username", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("password_hash", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("department", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("country", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("is_active", "BOOLEAN", mode="NULLABLE"),
            bigquery.SchemaField("created_at", "TIMESTAMP", mode="NULLABLE"),
            bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE"),
        ]
        table = bigquery.Table(table_ref, schema=schema)
        client.create_table(table, exists_ok=True)


def hash_password(password: str) -> str:
    """One-way salted hash — store this, never the plaintext password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_credentials(username: str, password: str) -> dict | None:
    """Check `username`/`password` against BigQuery.

    Returns {"userId", "department", "country"} on success. Returns None for
    every failure case (unknown user, wrong password, disabled account) —
    callers must not distinguish these in the response, to avoid leaking
    which usernames exist.
    """
    from google.cloud import bigquery
    from google.cloud.exceptions import NotFound

    if not username or not password:
        return None

    client = _get_client()
    query = f"SELECT username, password_hash, department, country, is_active FROM {_TABLE_FQN} WHERE LOWER(username) = @username_lower LIMIT 1"  # nosec B608
    try:
        job = client.query(
            query,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("username_lower", "STRING", username.lower())]
            ),
        )
        rows = list(job.result())
    except NotFound:
        logger.info("Users table not found in BigQuery; creating table.")
        try:
            ensure_users_table(client)
        except Exception:
            logger.exception("Failed to auto-create users table.")
        return None
    except Exception as e:
        if "not found" in str(e).lower():
            logger.info("Users table or dataset not found in BigQuery; creating table.")
            try:
                ensure_users_table(client)
            except Exception:
                logger.exception("Failed to auto-create users table.")
            return None
        raise

    if not rows:
        return None

    row = rows[0]
    if not row["is_active"]:
        return None
    if not bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8")):
        return None

    return {"userId": row["username"], "department": row["department"], "country": row["country"]}
