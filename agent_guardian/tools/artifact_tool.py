from __future__ import annotations

"""
artifact_tool.py — Reads files uploaded via ADK web UI from artifact storage.

When a user uploads a file through the ADK web interface, the file is stored as
an ADK artifact (not a regular file system path). This tool loads the artifact
bytes from the ADK artifact service and processes the content appropriately.
"""
import logging
from google.adk.tools.tool_context import ToolContext
from ..config import Config

logger = logging.getLogger(__name__)
_cfg = Config()


from agent_guardian.utils.ipynb_utils import preprocess_ipynb_content


def _preprocess_ipynb(raw_json: str) -> str:
    """Extracts code and markdown cells from a Jupyter Notebook JSON string.
    Delegates to the central utility.
    """
    return preprocess_ipynb_content(raw_json)


MAX_ARTIFACT_PAYLOAD_BYTES = 10 * 1024 * 1024  # 10 MB maximum payload


async def read_artifact_file(filename: str, tool_context: ToolContext) -> dict:
    """
    Reads a file uploaded via the ADK web UI from artifact storage.

    This tool should be used when the user has uploaded a file (e.g. a .py, .zip,
    or .ipynb file) directly through the chat interface. ADK stores uploaded files
    as artifacts identified by their filename.

    Args:
        filename: The name of the uploaded file (e.g. "Text_Summarization.ipynb", "project.zip").

    Returns:
        A dict with:
          - "status": "success" or "error"
          - "codebase": Formatted string with file contents ready for review.
          - "file_count": Number of files successfully read.
          - "message": Human-readable status message.
    """
    import os
    from pathlib import Path

    if not filename or not filename.strip():
        return {
            "status": "error",
            "codebase": "",
            "file_count": 0,
            "message": "No filename provided.",
        }

    clean_filename = os.path.basename(filename.strip())
    if not clean_filename or clean_filename in (".", ".."):
        return {
            "status": "error",
            "codebase": "",
            "file_count": 0,
            "message": "Invalid filename provided.",
        }

    if tool_context is None:
        return {
            "status": "error",
            "codebase": "",
            "file_count": 0,
            "message": "Tool context unavailable. Artifact service cannot be accessed.",
        }

    try:
        artifact = await tool_context.load_artifact(filename=clean_filename)
    except Exception as e:
        logger.warning(f"read_artifact_file: Failed to load artifact '{clean_filename}': {e}")
        return {
            "status": "error",
            "codebase": "",
            "file_count": 0,
            "message": f"Could not load artifact '{clean_filename}': {e}",
        }

    if artifact is None:
        return {
            "status": "error",
            "codebase": "",
            "file_count": 0,
            "message": f"Artifact '{clean_filename}' not found in session storage.",
        }

    # Extract raw bytes from the artifact Part
    try:
        inline_data = getattr(artifact, "inline_data", None) or getattr(artifact, "inlineData", None)
        if inline_data and getattr(inline_data, "data", None):
            raw_bytes = inline_data.data
        elif hasattr(artifact, "data") and artifact.data:
            raw_bytes = artifact.data
        else:
            return {
                "status": "error",
                "codebase": "",
                "file_count": 0,
                "message": f"Artifact '{clean_filename}' contains no data payload.",
            }

        if isinstance(raw_bytes, str):
            import base64
            try:
                raw_bytes = base64.b64decode(raw_bytes)
            except Exception:
                raw_bytes = raw_bytes.encode("utf-8")
    except Exception as e:
        logger.warning(f"read_artifact_file: Failed to extract artifact bytes: {e}")
        return {
            "status": "error",
            "codebase": "",
            "file_count": 0,
            "message": f"Failed to extract file content: {e}",
        }

    lower_name = clean_filename.lower()

    # Handle ZIP archives uploaded as artifacts
    if lower_name.endswith(".zip"):
        import io
        import zipfile
        from agent_guardian.tools.file_tool import (
            is_ingestible_file,
            in_skipped_dir,
            MAX_FILE_SIZE_BYTES,
        )

        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zf:
                infolist = zf.infolist()
                collected_files: dict[str, str] = {}

                for info in infolist:
                    if info.filename.endswith("/") or info.filename.endswith("\\"):
                        continue
                    parts = Path(info.filename).parts
                    if in_skipped_dir(parts):
                        continue
                    if not is_ingestible_file(info.filename):
                        continue
                    if info.file_size > MAX_FILE_SIZE_BYTES:
                        continue

                    with zf.open(info.filename) as member_file:
                        data = member_file.read(MAX_FILE_SIZE_BYTES + 1)
                        if len(data) <= MAX_FILE_SIZE_BYTES:
                            decoded = data.decode("utf-8", errors="replace")
                            if Path(info.filename).suffix.lower() == ".ipynb":
                                decoded = _preprocess_ipynb(decoded)
                            collected_files[info.filename] = decoded

                if not collected_files:
                    return {
                        "status": "error",
                        "codebase": "",
                        "file_count": 0,
                        "message": f"No eligible source files found in zip artifact '{clean_filename}'.",
                    }

                lines = ["=== DIRECTORY STRUCTURE ===", "  [LOGIC]"]
                for f in sorted(collected_files.keys()):
                    lines.append(f"    {f}")
                lines.append("\n=== FILE CONTENTS ===")
                for fname, fcontent in sorted(collected_files.items()):
                    lines.append(f"\n--- {fname} ---\n{fcontent}")

                codebase = "\n".join(lines)
                logger.info(f"read_artifact_file: Unpacked ZIP '{clean_filename}' with {len(collected_files)} files")
                return {
                    "status": "success",
                    "codebase": codebase,
                    "file_count": len(collected_files),
                    "message": f"Successfully unpacked and read {len(collected_files)} files from ZIP artifact '{clean_filename}'.",
                }
        except zipfile.BadZipFile as e:
            return {
                "status": "error",
                "codebase": "",
                "file_count": 0,
                "message": f"Malformed ZIP artifact '{clean_filename}': {e}",
            }

    # Handle single file artifacts
    raw_text = raw_bytes.decode("utf-8", errors="replace")
    if lower_name.endswith(".ipynb"):
        content = _preprocess_ipynb(raw_text)
        label = "Jupyter Notebook"
    else:
        content = raw_text
        label = "Source File"

    if not content.strip():
        return {
            "status": "error",
            "codebase": "",
            "file_count": 0,
            "message": f"The file '{clean_filename}' appears to be empty after processing.",
        }

    # Truncate content if it exceeds the limit
    truncated = False
    if len(content) > _cfg.max_codebase_chars:
        content = (
            content[: _cfg.max_codebase_chars] + "\n\n[TRUNCATED: File content truncated to stay within token limits]"
        )
        truncated = True

    codebase = (
        f"=== DIRECTORY STRUCTURE ===\n"
        f"  [LOGIC]\n"
        f"    {clean_filename}\n\n"
        f"=== FILE CONTENTS ===\n\n"
        f"--- {clean_filename} ---\n"
        f"{content}\n"
    )

    if truncated:
        codebase += "\n[!] WARNING: Content has been partially truncated to prevent token limit errors."

    logger.info(f"read_artifact_file: Successfully loaded '{clean_filename}' ({label}, {len(content)} chars)")
    return {
        "status": "success",
        "codebase": codebase,
        "file_count": 1,
        "message": f"Successfully read '{clean_filename}' ({label}, {len(content)} chars).{' (TRUNCATED)' if truncated else ''}",
    }


async def save_artifact_file(
    filename: str,
    content: str,
    mime_type: str = "text/plain",
    tool_context: ToolContext | None = None,
) -> dict:
    """
    Saves text content as an ADK artifact in session storage (persisted to GCS in production).

    Use this tool to persist generated audit reports, remediation patches, architectural diagrams,
    or summary documents directly to Google Cloud Storage (via GcsArtifactService) or local artifact storage.

    Args:
        filename: Name of the artifact file (e.g. "report.html", "remediation.diff", "audit_summary.json").
        content: Raw text or string payload to save as the artifact content.
        mime_type: MIME type of the file (e.g. "text/html", "text/plain", "application/json").

    Returns:
        A dict with:
          - "status": "success" or "error"
          - "filename": Name of the saved file
          - "bytes_saved": Size of the payload in bytes
          - "message": Human-readable status message
    """
    import os

    if not filename or not filename.strip():
        return {
            "status": "error",
            "filename": "",
            "bytes_saved": 0,
            "message": "No filename provided.",
        }

    clean_filename = os.path.basename(filename.strip())
    if not clean_filename or clean_filename in (".", ".."):
        return {
            "status": "error",
            "filename": "",
            "bytes_saved": 0,
            "message": "Invalid filename provided.",
        }

    if tool_context is None:
        return {
            "status": "error",
            "filename": clean_filename,
            "bytes_saved": 0,
            "message": "Tool context unavailable. Artifact service cannot be accessed.",
        }

    if content is None:
        content = ""

    data_bytes = content.encode("utf-8")
    if len(data_bytes) > MAX_ARTIFACT_PAYLOAD_BYTES:
        return {
            "status": "error",
            "filename": clean_filename,
            "bytes_saved": 0,
            "message": f"Artifact payload exceeds maximum allowed size ({len(data_bytes)} > {MAX_ARTIFACT_PAYLOAD_BYTES} bytes).",
        }

    try:
        from google.genai import types

        artifact = types.Part(inline_data=types.Blob(data=data_bytes, mime_type=mime_type))
        version = await tool_context.save_artifact(filename=clean_filename, artifact=artifact)
        logger.info(f"save_artifact_file: Successfully saved artifact '{clean_filename}' (version={version}, {len(data_bytes)} bytes)")
        return {
            "status": "success",
            "filename": clean_filename,
            "version": version,
            "bytes_saved": len(data_bytes),
            "message": f"Successfully saved artifact '{clean_filename}' ({len(data_bytes)} bytes).",
        }
    except Exception as e:
        logger.warning(f"save_artifact_file: Failed to save artifact '{clean_filename}': {e}")
        return {
            "status": "error",
            "filename": clean_filename,
            "bytes_saved": 0,
            "message": f"Failed to save artifact '{clean_filename}': {e}",
        }

