from __future__ import annotations

"""
Artifact Factory for Agent Guardian.

Provides a unified factory to initialize ADK ArtifactServices based on environment
configuration (Google Cloud Storage, File System, or InMemory fallback).
"""

import logging
import os

from google.adk.artifacts import (
    BaseArtifactService,
    InMemoryArtifactService,
)

logger = logging.getLogger(__name__)


def get_artifact_service(
    service_uri: str | None = None,
    bucket_name: str | None = None,
) -> BaseArtifactService:
    """Instantiates and returns an ADK ArtifactService based on configuration.

    Selection priority:
    1. If `service_uri` or `ARTIFACT_SERVICE_URI` starts with 'gs://' or `bucket_name` is provided:
       instantiates `GcsArtifactService`.
    2. If `service_uri` or `ARTIFACT_SERVICE_URI` starts with 'file://' or points to a local directory:
       instantiates `FileArtifactService`.
    3. Default fallback: instantiates `InMemoryArtifactService`.
    """
    resolved_uri = (service_uri or os.environ.get("ARTIFACT_SERVICE_URI") or "").strip()
    resolved_bucket = (bucket_name or os.environ.get("ARTIFACT_BUCKET") or "").strip()

    # 1. Google Cloud Storage Artifact Service
    if resolved_uri.startswith("gs://") or resolved_bucket:
        try:
            target_bucket = resolved_bucket
            if resolved_uri.startswith("gs://"):
                target_bucket = resolved_uri[5:].strip("/")

            if target_bucket:
                from google.adk.artifacts import GcsArtifactService

                logger.info(
                    "Initializing GcsArtifactService for bucket: %s (uri=%s)",
                    target_bucket,
                    resolved_uri or f"gs://{target_bucket}",
                )
                return GcsArtifactService(bucket_name=target_bucket)
        except Exception as e:
            logger.error(
                "Failed to initialize GcsArtifactService (%s). Falling back to InMemoryArtifactService.",
                e,
                exc_info=True,
            )
            return InMemoryArtifactService()

    # 2. File Artifact Service for local disk persistence
    if resolved_uri.startswith("file://") or (resolved_uri and not resolved_uri.startswith("gs://")):
        try:
            from google.adk.artifacts import FileArtifactService

            local_path = resolved_uri[7:] if resolved_uri.startswith("file://") else resolved_uri
            logger.info("Initializing FileArtifactService at directory: %s", local_path)
            return FileArtifactService(root_dir=local_path)
        except Exception as e:
            logger.error(
                "Failed to initialize FileArtifactService (%s). Falling back to InMemoryArtifactService.",
                e,
                exc_info=True,
            )
            return InMemoryArtifactService()

    logger.info("Using default InMemoryArtifactService.")
    return InMemoryArtifactService()
