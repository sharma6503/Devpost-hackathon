"""Create or update an admin-provisioned login account in BigQuery.

There is no public signup — this is how an admin adds/updates a user.

Usage:
    uv run python scripts/seed_bq_user.py --username jdoe --department Sales --country US
    (you'll be prompted for the password so it never lands in shell history)
"""

from __future__ import annotations

import argparse
import getpass

from google.cloud import bigquery

from agent_guardian.auth import BQ_PROJECT, _TABLE_FQN, ensure_users_table, hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True, help="Username or email for operator")
    parser.add_argument("--password", required=False, default=None, help="Plaintext password (if omitted, will prompt securely)")
    parser.add_argument("--department", required=False, default="Security Engineering", help="User department (default: Security Engineering)")
    parser.add_argument("--country", required=False, default="US", help="User country code (default: US)")
    parser.add_argument("--deactivate", action="store_true", help="Disable this account instead of creating/updating it")
    args = parser.parse_args()

    client = bigquery.Client(project=BQ_PROJECT)
    ensure_users_table(client)

    if args.deactivate:
        password_hash = None
    elif args.password is not None:
        password_hash = hash_password(args.password)
    else:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            raise SystemExit("Passwords did not match.")
        password_hash = hash_password(password)

    query = f"""
        MERGE {_TABLE_FQN} T
        USING (SELECT @username AS username) S
        ON T.username = S.username
        WHEN MATCHED THEN UPDATE SET
            password_hash = COALESCE(@password_hash, T.password_hash),
            department = @department,
            country = @country,
            is_active = @is_active,
            updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT (username, password_hash, department, country, is_active, created_at, updated_at)
        VALUES (@username, @password_hash, @department, @country, @is_active, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
    """
    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("username", "STRING", args.username),
                bigquery.ScalarQueryParameter("password_hash", "STRING", password_hash),
                bigquery.ScalarQueryParameter("department", "STRING", args.department),
                bigquery.ScalarQueryParameter("country", "STRING", args.country),
                bigquery.ScalarQueryParameter("is_active", "BOOL", not args.deactivate),
            ]
        ),
    )
    job.result()
    action = "Deactivated" if args.deactivate else "Upserted"
    print(f"{action} user {args.username!r}.")


if __name__ == "__main__":
    main()
