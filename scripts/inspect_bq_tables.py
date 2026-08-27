"""Inspect all tables and rows in agent-related datasets."""
from __future__ import annotations
from google.cloud import bigquery
import os

project = (
    os.environ.get("BQ_PROJECT")
    or os.environ.get("GOOGLE_CLOUD_PROJECT")
    or os.environ.get("GCP_PROJECT")
    or "imgcp-51c5a39739fbedcd"
)
client = bigquery.Client(project=project)

target_datasets = [
    "agent_gaurdian",
    "agent_guardian",
    "agent_audit_logs",
    "agent_logs",
    "agentlog",
    "gcp_audit_logs",
]

print(f"Connecting to GCP Project: {project}\n")

for ds_id in target_datasets:
    try:
        tables = list(client.list_tables(ds_id))
        print(f"=== Dataset: {ds_id} (Tables: {len(tables)}) ===")
        for t in tables:
            fqn = f"`{project}.{ds_id}.{t.table_id}`"
            try:
                query = f"SELECT count(*) as c FROM {fqn}"
                count = list(client.query(query).result())[0]["c"]
                print(f"  Table: {t.table_id} -> {count} rows")
                if count > 0:
                    sample_query = f"SELECT * FROM {fqn} LIMIT 2"
                    sample_rows = list(client.query(sample_query).result())
                    for s in sample_rows:
                        print(f"    Sample: {dict(s)}")
            except Exception as e:
                print(f"  Table: {t.table_id} -> Query note: {e}")
        print()
    except Exception as e:
        print(f"Dataset {ds_id} error: {e}\n")
