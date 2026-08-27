import sys, os
sys.path.insert(0, os.path.abspath("."))
from agent_guardian.auth import _get_client
client = _get_client()
table_id = f"`{client.project}.agent_gaurdian.users`"
try:
    rows = list(client.query(f"SELECT * FROM {table_id}").result())
    print(f"agent_gaurdian.users has {len(rows)} rows:")
    for r in rows:
        print(dict(r))
except Exception as e:
    print("Error querying agent_gaurdian.users:", e)
