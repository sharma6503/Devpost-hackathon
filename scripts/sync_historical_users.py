import sys, os
sys.path.insert(0, os.path.abspath("."))
from agent_guardian.auth import _get_client
from google.cloud import bigquery

client = _get_client()

# Fetch all rows from agent_gaurdian.users (location: us-central1)
query = f"SELECT username, password_hash, department, country, is_active, created_at, updated_at FROM `{client.project}.agent_gaurdian.users`"
rows = list(client.query(query, location="us-central1").result())

print(f"Retrieved {len(rows)} users from agent_gaurdian.users (us-central1)")

# Ensure destination table in agent_guardian exists (location: US)
from agent_guardian.auth import ensure_users_table
ensure_users_table()

# Insert or update each row in destination (location: US)
for r in rows:
    user_dict = dict(r)
    # Check if exists in agent_guardian
    check_q = f"SELECT count(*) as c FROM `{client.project}.agent_guardian.users` WHERE LOWER(username) = LOWER(@uname)"
    job_cfg = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("uname", "STRING", user_dict["username"])]
    )
    exists = list(client.query(check_q, job_config=job_cfg, location="US").result())[0]["c"] > 0
    if not exists:
        insert_q = f"""
        INSERT INTO `{client.project}.agent_guardian.users` (username, password_hash, department, country, is_active, created_at, updated_at)
        VALUES (@username, @password_hash, @department, @country, @is_active, @created_at, @updated_at)
        """
        insert_cfg = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("username", "STRING", user_dict["username"]),
                bigquery.ScalarQueryParameter("password_hash", "STRING", user_dict["password_hash"]),
                bigquery.ScalarQueryParameter("department", "STRING", user_dict.get("department", "Engineering")),
                bigquery.ScalarQueryParameter("country", "STRING", user_dict.get("country", "US")),
                bigquery.ScalarQueryParameter("is_active", "BOOL", user_dict.get("is_active", True)),
                bigquery.ScalarQueryParameter("created_at", "TIMESTAMP", user_dict["created_at"]),
                bigquery.ScalarQueryParameter("updated_at", "TIMESTAMP", user_dict["updated_at"]),
            ]
        )
        client.query(insert_q, job_config=insert_cfg, location="US").result()
        print(f"  + Synced user: {user_dict['username']}")
    else:
        print(f"  = Already exists: {user_dict['username']}")

count = list(client.query(f"SELECT count(*) as c FROM `{client.project}.agent_guardian.users`", location="US").result())[0]["c"]
print(f"\nCompleted! agent_guardian.users now has {count} total users.")
