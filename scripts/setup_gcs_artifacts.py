#!/usr/bin/env python
from __future__ import annotations

"""
Setup Google Cloud Storage (GCS) bucket for ADK Artifact Persistence.

Provisions the GCS bucket used by Agent Guardian's GcsArtifactService to store
generated audit reports (HTML), charts, remediation patches, and session artifacts.
"""

import os
import sys
import argparse
import subprocess
from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Provision GCS bucket for ADK artifacts storage")
    parser.add_argument(
        "--project",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT", "imgcp-51c5a39739fbedcd"),
        help="GCP Project ID",
    )
    parser.add_argument(
        "--bucket",
        default=os.environ.get("ARTIFACT_BUCKET") or "agentguardian-prod-artifacts",
        help="GCS Bucket name for artifacts (without gs:// prefix)",
    )
    parser.add_argument(
        "--location",
        default=os.environ.get("GCP_REGION") or "us-central1",
        help="GCS bucket location/region",
    )
    args = parser.parse_args()

    bucket_name = args.bucket.replace("gs://", "").strip("/")
    project_id = args.project
    location = args.location

    print("=" * 70)
    print("Agent Guardian — ADK GCS Artifact Storage Provisioner")
    print("=" * 70)
    print(f"Project ID: {project_id}")
    print(f"Bucket:     gs://{bucket_name}")
    print(f"Location:   {location}")
    print("=" * 70)

    # 1. Try using google-cloud-storage Python SDK first
    try:
        from google.cloud import storage

        client = storage.Client(project=project_id)
        bucket = client.bucket(bucket_name)

        if not bucket.exists():
            print(f"Creating GCS bucket 'gs://{bucket_name}' in '{location}'...")
            bucket = client.create_bucket(bucket, location=location, project=project_id)
            # Enable uniform bucket-level access
            bucket.iam_configuration.uniform_bucket_level_access_enabled = True
            bucket.patch()
            print(f"[OK] Successfully created bucket gs://{bucket_name} with Uniform Bucket-Level Access.")
        else:
            print(f"[OK] Bucket 'gs://{bucket_name}' already exists.")
            # Ensure uniform bucket-level access
            if not bucket.iam_configuration.uniform_bucket_level_access_enabled:
                bucket.iam_configuration.uniform_bucket_level_access_enabled = True
                bucket.patch()
                print(f"[OK] Enabled Uniform Bucket-Level Access on gs://{bucket_name}.")

        print("\nArtifact Storage Configuration:")
        print(f"  ARTIFACT_SERVICE_URI=gs://{bucket_name}")
        print(f"  ARTIFACT_BUCKET={bucket_name}")
        print("\nAll ADK artifacts (reports, diagrams, diffs) will now persist across runs.")
        return 0

    except ImportError:
        print("[INFO] google-cloud-storage SDK not found in environment; falling back to gcloud CLI...")
    except Exception as e:
        print(f"[WARN] Python GCS client encountered: {e}. Falling back to gcloud CLI...")

    # 2. Fallback to gcloud CLI
    try:
        cmd = [
            "gcloud",
            "storage",
            "buckets",
            "create",
            f"gs://{bucket_name}",
            f"--project={project_id}",
            f"--location={location}",
            "--uniform-bucket-level-access",
        ]
        print(f"Executing: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 or "already exists" in res.stderr.lower():
            print(f"[OK] GCS bucket gs://{bucket_name} is ready.")
            print(f"\nSet environment variable: ARTIFACT_SERVICE_URI=gs://{bucket_name}")
            return 0
        else:
            print(f"[ERROR] Failed to create bucket via gcloud: {res.stderr}")
            return 1
    except Exception as e:
        print(f"[ERROR] Could not run gcloud: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
