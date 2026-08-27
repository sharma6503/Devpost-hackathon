import sys, os
sys.path.insert(0, os.path.abspath("."))
from agent_guardian.auth import _get_client
client = _get_client()

tables = list(client.list_tables("agent_gaurdian"))
print("Tables in agent_gaurdian:")
for t in tables:
    fqn = f"`{client.project}.agent_gaurdian.{t.table_id}`"
    try:
        cnt = list(client.query(f"SELECT count(*) as c FROM {fqn}").result())[0]["c"]
        print(f"  {t.table_id}: {cnt} rows")
    except Exception as e:
        print(f"  {t.table_id}: error ({e})")
