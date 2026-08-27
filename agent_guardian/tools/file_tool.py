from __future__ import annotations
import os
import zipfile
import concurrent.futures
import shutil
import logging
from pathlib import Path
from google.adk.tools.tool_context import ToolContext
from ..config import Config

logger = logging.getLogger(__name__)
_cfg = Config()

# File extensions we care about for code review
CODE_EXTENSIONS = {
    ".py",
    ".ts",
    ".js",
    ".go",
    ".java",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".cs",
    ".rs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".kts",
    ".m",
    ".scala",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".xml",
    ".html",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".md",
    ".txt",
    ".env.example",
    ".dockerfile",
    ".tf",
    ".sh",
    ".bash",
    ".zsh",
    ".ipynb",  # Jupyter Notebooks
}


from agent_guardian.utils.ipynb_utils import preprocess_ipynb_content


def _preprocess_ipynb(raw_json: str) -> str:
    """Extracts code and markdown cells from a Jupyter Notebook JSON string.
    Delegates to the central utility.
    """
    return preprocess_ipynb_content(raw_json)


MAX_FILE_SIZE_BYTES = _cfg.max_file_size_kb * 1024
MAX_WORKERS = 8

SKIP_DIRS = {
    "node_modules",
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    ".next",
    "dist",
    "build",
}

# Denylist of binary / media / compiled extensions we must NEVER ingest as text.
# Everything NOT in this set is treated as ingestible source/text. This is the
# inverse of the old CODE_EXTENSIONS allowlist, which silently dropped legitimate
# files (go.mod, .proto, .graphql, lockfiles, Dockerfiles with odd names, etc.).
SKIP_EXTENSIONS = {
    # images / media
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".svg",
    ".webp",
    ".tif",
    ".tiff",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".mp3",
    ".wav",
    ".flac",
    ".ogg",
    ".m4a",
    # fonts
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".eot",
    # archives
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".jar",
    ".war",
    ".ear",
    # compiled / native binaries
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".bin",
    ".o",
    ".a",
    ".obj",
    ".lib",
    ".pyc",
    ".pyo",
    ".class",
    ".wasm",
    # office / binary docs
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    # data blobs / serialized models
    ".db",
    ".sqlite",
    ".sqlite3",
    ".parquet",
    ".npy",
    ".npz",
    ".pkl",
    ".pickle",
    ".h5",
    ".hdf5",
    ".pt",
    ".pth",
    ".ckpt",
    ".onnx",
    ".safetensors",
}

# Sensitive credential / key file names and extensions to protect from unintended ingestion
SENSITIVE_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.staging",
    ".gitconfig",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "credentials.json",
    "service_account.json",
    "service-account.json",
    "service_account_key.json",
    "authorized_keys",
    "known_hosts",
    "passwd",
    "shadow",
    "master.key",
    "secrets.yml",
    "secrets.yaml",
}

SENSITIVE_EXTENSIONS = {
    ".pem",
    ".key",
    ".pkcs12",
    ".p12",
    ".pfx",
    ".kdbx",
    ".keystore",
    ".jks",
}


def is_ingestible_file(name: str) -> bool:
    """Denylist filter: ingest any file that is not a known binary/media or sensitive credential type."""
    p = Path(name)
    base = p.name.lower()
    suffix = p.suffix.lower()
    if suffix in SKIP_EXTENSIONS or suffix in SENSITIVE_EXTENSIONS:
        return False
    if base in SENSITIVE_FILENAMES and base != ".env.example":
        return False
    if base.startswith(".env.") and not base.endswith(".example"):
        return False
    return True


def in_skipped_dir(parts) -> bool:
    """True if any path segment is a generated/vendored directory we skip."""
    return any(part in SKIP_DIRS for part in parts)


def parse_uploaded_files(file_paths: list[str], tool_context: ToolContext = None) -> dict:
    """
    Reads and consolidates source code from a list of local file paths or a ZIP archive.
    Uses ThreadPoolExecutor for parallel I/O to optimize multi-file ingestion.
    ZIP files are processed entirely in-memory as streams, but also physically
    extracted to a session-specific ADK artifact directory if possible.

    Returns:
        A dict with:
          - "status": "success" or "error"
          - "codebase": Formatted string with directory structure + file contents.
          - "summary": List of files found by category (logic, config, docs).
          - "file_count": Number of files successfully read.
    """
    if not file_paths:
        return {
            "status": "error",
            "codebase": "",
            "file_count": 0,
            "skipped": ["No file paths provided."],
        }

    collected_files: dict[str, str] = {}
    skipped: list[str] = []

    # Defensive backstop: if the LLM passes a bare filename / relative path that
    # doesn't exist, try to auto-resolve it under the session's
    # `source_artifact_path` (the extracted-zip dir). This stops tool-call loops
    # caused by the model guessing leaf filenames like "models.py".
    artifact_root: Path | None = None
    if tool_context is not None:
        try:
            sap = (tool_context.state or {}).get("source_artifact_path")
            if sap:
                artifact_root = Path(sap)
        except Exception as e:
            logger.warning(f"parse_uploaded_files: could not read source_artifact_path from state: {e}")
            artifact_root = None

    def _resolve_path(p: str) -> Path:
        candidate = Path(p)
        if candidate.exists():
            return candidate
        if artifact_root and artifact_root.exists():
            joined = artifact_root / p.lstrip("/\\")
            if joined.exists():
                return joined
            # Last-resort: glob for the basename anywhere under artifact_root.
            matches = list(artifact_root.rglob(Path(p).name))
            if len(matches) == 1:
                return matches[0]
        return candidate  # caller will detect non-existence

    # Each task is a tuple: (callable, (args...), display_name)
    all_eligible_tasks: list[tuple] = []

    try:
        # Wipe the session artifact dir at most once per call: the first ZIP
        # clears any prior upload turn's files; later ZIPs in the same call
        # merge into the same dir instead of clobbering each other.
        artifact_cleaned = False
        for path_str in file_paths:
            path = _resolve_path(path_str)
            if not path.exists():
                hint = f" (resolved against source_artifact_path={artifact_root})" if artifact_root else ""
                skipped.append(f"{os.path.basename(path_str)}: Not found{hint}")
                continue

            if path.suffix.lower() == ".zip":
                # Hardening: Check limits before extraction
                try:
                    with zipfile.ZipFile(path, "r") as zf:
                        infolist = zf.infolist()

                        # 1. MAX_FILES_PER_ZIP check
                        if len(infolist) > _cfg.max_files_per_zip:
                            msg = f"ZIP '{os.path.basename(path_str)}' exceeds max file limit ({len(infolist)} > {_cfg.max_files_per_zip})."
                            logger.error(msg)
                            return {
                                "status": "error",
                                "codebase": f"[SYSTEM ERROR: {msg}]",
                                "file_count": 0,
                            }

                        # 2. MAX_TOTAL_ZIP_SIZE_KB check (uncompressed)
                        total_size = sum(info.file_size for info in infolist)
                        if total_size > _cfg.max_total_zip_size_kb * 1024:
                            msg = f"ZIP '{os.path.basename(path_str)}' uncompressed size too large ({total_size // 1024} KB > {_cfg.max_total_zip_size_kb} KB)."
                            logger.error(msg)
                            return {
                                "status": "error",
                                "codebase": f"[SYSTEM ERROR: {msg}]",
                                "file_count": 0,
                            }

                        # Extraction process. ADK's ToolContext has no `session_id`
                        # attribute — the id lives on `tool_context.session.id`.
                        session_id = None
                        if tool_context is not None:
                            raw_sid = getattr(tool_context, "session_id", None)
                            if isinstance(raw_sid, (str, int)) and str(raw_sid).strip():
                                session_id = str(raw_sid).strip()
                            else:
                                session_obj = getattr(tool_context, "session", None)
                                raw_sid = getattr(session_obj, "id", None)
                                if isinstance(raw_sid, (str, int)) and str(raw_sid).strip():
                                    session_id = str(raw_sid).strip()
                        if session_id:
                            import re as _re
                            clean_sid = _re.sub(r"[^a-zA-Z0-9_-]", "", str(session_id))
                            if clean_sid:
                                base_artifacts = (Path.cwd() / ".adk" / "artifacts").resolve()
                                artifact_dir = (base_artifacts / clean_sid / "source").resolve()
                                if artifact_dir.is_relative_to(base_artifacts):
                                    # Clean stale files from a PRIOR upload turn before extracting the
                                    # first ZIP of this call; otherwise deleted/renamed files linger on
                                    # disk and can be resolved by _resolve_path. Wipe only once per call
                                    # (guarded by artifact_cleaned) so multiple ZIPs passed in one call
                                    # merge into the same dir instead of each wiping the previous one's.
                                    if artifact_dir.exists() and not artifact_cleaned:
                                        try:
                                            shutil.rmtree(artifact_dir)
                                        except Exception as _clean_err:
                                            logger.warning(f"parse_uploaded_files: could not clean artifact dir: {_clean_err}")
                                    artifact_cleaned = True
                                    artifact_dir.mkdir(parents=True, exist_ok=True)
                                    _unzip_to_target(path, artifact_dir, skipped)
                                    tool_context.state["source_artifact_path"] = str(artifact_dir.absolute())

                        for info in infolist:
                            name = info.filename
                            if name.endswith("/"):
                                continue  # Skip directories

                            parts = Path(name).parts
                            if in_skipped_dir(parts):
                                continue

                            if not is_ingestible_file(name):
                                continue

                            if info.file_size > MAX_FILE_SIZE_BYTES:
                                skipped.append(f"{name}: exceeds individual file size limit")
                                continue

                            all_eligible_tasks.append((_read_zip_member_safe, (path, name), name))
                except zipfile.BadZipFile:
                    skipped.append(f"{os.path.basename(path_str)}: Bad ZIP file")
            elif path.is_dir():
                _gather_paths(path, all_eligible_tasks, skipped)
            else:
                _gather_paths(path, all_eligible_tasks, skipped, single_file=True)

        if not all_eligible_tasks:
            return {
                "status": "error",
                "codebase": "[SYSTEM ERROR: No readable source files found in the provided paths.]",
                "file_count": 0,
                "skipped": skipped,
            }

        # Parallel Read
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_name = {executor.submit(func, *args): name for func, args, name in all_eligible_tasks}
            for future in concurrent.futures.as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    content = future.result()
                    if content:
                        collected_files[name] = content
                    else:
                        skipped.append(f"{name}: Empty content or read failure")
                except Exception as e:
                    skipped.append(f"{name}: Read error - {str(e)}")

        # Organize by category for experts
        categories = {"logic": [], "config": [], "docs": [], "other": []}
        for fname in collected_files.keys():
            ext = Path(fname).suffix.lower()
            if ext in {".py", ".ts", ".js", ".go", ".java", ".ipynb"}:
                categories["logic"].append(fname)
            elif ext in {".yaml", ".yml", ".toml", ".json", ".env.example"}:
                categories["config"].append(fname)
            elif ext in {".md", ".txt"}:
                categories["docs"].append(fname)
            else:
                categories["other"].append(fname)

        # Format output
        lines = ["=== DIRECTORY STRUCTURE ==="]
        for cat, files in categories.items():
            if files:
                lines.append(f"  [{cat.upper()}]")
                for f in sorted(files):
                    lines.append(f"    {f}")

        if skipped:
            lines.append("\n=== FETCH WARNINGS ===")
            for s in skipped:
                lines.append(f"  [!] {s}")

        lines.append("\n=== FILE CONTENTS ===")

        total_chars = sum(len(line) for line in lines)
        truncated_any = False

        for fname, content in sorted(collected_files.items()):
            ext = Path(fname).suffix.lstrip(".") or ""
            # Map common extensions to markdown languages
            lang_map = {
                "py": "python",
                "js": "javascript",
                "ts": "typescript",
                "yml": "yaml",
                "yaml": "yaml",
            }
            lang = lang_map.get(ext.lower(), ext.lower())

            header = f"\n--- {fname} ---\n```{lang}\n"
            footer = "\n```"

            # Check if adding this file exceeds the limit
            if total_chars + len(header) + len(content) + len(footer) > _cfg.max_codebase_chars:
                lines.append(f"\n--- {fname} ---\n[TRUNCATED: File omitted to stay within token limits]")
                truncated_any = True
                continue

            lines.append(f"{header}{content}{footer}")
            total_chars += len(lines[-1])

        if truncated_any:
            lines.append(
                "\n[!] WARNING: Codebase has been partially truncated to prevent token limit errors. Use specific file paths to review missing modules."
            )

        return {
            "status": "success",
            "codebase": "\n".join(lines),
            "summary": categories,
            "file_count": len(collected_files),
            "skipped": skipped,
        }
    except Exception as e:
        # Propagate so the framework's retry machinery (ReflectAndRetryToolPlugin /
        # GlobalResiliencePlugin) can handle it — swallowing here disables ADK 2.0
        # automatic retries for this step.
        logger.error(f"parse_uploaded_files: ingestion failed: {e}")
        raise


def _gather_paths(root: Path, task_list: list, skipped: list, single_file=False) -> None:
    def is_eligible(p: Path):
        if not is_ingestible_file(p.name):
            return False
        if p.stat().st_size > MAX_FILE_SIZE_BYTES:
            skipped.append(f"{os.path.basename(str(p))}: too large")
            return False
        return True

    if single_file:
        if is_eligible(root):
            task_list.append((_read_file_safe, (root,), os.path.basename(str(root))))
        return

    for item in root.rglob("*"):
        if item.is_file() and not in_skipped_dir(item.parts) and is_eligible(item):
            task_list.append((_read_file_safe, (item,), str(item.relative_to(root))))


def _read_file_safe(path: Path) -> str:
    try:
        if path.is_symlink():
            logger.debug(f"Skipping symlink {path}")
            return ""
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read(MAX_FILE_SIZE_BYTES + 1)
        if len(raw) > MAX_FILE_SIZE_BYTES:
            logger.debug(f"Skipping {path}: exceeds {MAX_FILE_SIZE_BYTES} byte limit")
            return ""
        if path.suffix.lower() == ".ipynb":
            return _preprocess_ipynb(raw)
        return raw
    except Exception as e:
        logger.error(f"Failed to read file {os.path.basename(str(path))}: {e}")
        return ""


def _read_zip_member_safe(zip_path: Path, member_name: str) -> str:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            with zf.open(member_name) as f:
                # Read at most MAX_FILE_SIZE_BYTES + 1 to prevent zip bombs
                data = f.read(MAX_FILE_SIZE_BYTES + 1)
                if len(data) > MAX_FILE_SIZE_BYTES:
                    logger.debug(f"Skipping ZIP member {member_name}: exceeds {MAX_FILE_SIZE_BYTES} byte limit")
                    return ""
                raw = data.decode("utf-8", errors="replace")
                if Path(member_name).suffix.lower() == ".ipynb":
                    return _preprocess_ipynb(raw)
                return raw
    except Exception as e:
        logger.error(f"Failed to read ZIP member {member_name}: {e}")
        return ""


def _unzip_to_target(zip_path: Path, target_dir: Path, skipped: list):
    """Physically extracts eligible code files from a ZIP archive to a given target directory with strict symlink and bomb guards."""
    try:
        import stat
        max_total_bytes = _cfg.max_total_zip_size_kb * 1024
        resolved_dir = target_dir.resolve()

        with zipfile.ZipFile(zip_path, "r") as zf:
            extract_tasks = []
            for name in zf.namelist():
                if name.endswith("/") or name.endswith("\\"):
                    continue

                parts = Path(name).parts
                if in_skipped_dir(parts):
                    continue

                if not is_ingestible_file(name):
                    continue

                info = zf.getinfo(name)
                # Ignore symlinks / hardlinks to prevent symlink traversal attacks
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    skipped.append(f"{name}: Ignored symlink archive member")
                    continue

                if info.file_size > MAX_FILE_SIZE_BYTES:
                    skipped.append(f"{name}: too large to extract to physical artifact")
                    continue

                extract_tasks.append(name)

            def _extract_member(member_name):
                try:
                    clean_name = member_name.lstrip("/\\")
                    resolved_target = (target_dir / clean_name).resolve()
                    if not resolved_target.is_relative_to(resolved_dir):
                        return f"{member_name}: Security error (directory traversal)"

                    target_parent = resolved_target.parent
                    if target_parent.is_symlink() or not target_parent.resolve().is_relative_to(resolved_dir):
                        return f"{member_name}: Security error (parent is symlink)"

                    target_parent.mkdir(parents=True, exist_ok=True)

                    if resolved_target.is_symlink():
                        return f"{member_name}: Security error (target is existing symlink)"

                    # Open a fresh handle for the thread to prevent ZipFile concurrency locks
                    # Bounded chunk copy to prevent decompression bomb
                    member_bytes = 0
                    with zipfile.ZipFile(zip_path, "r") as thread_zf:
                        with thread_zf.open(member_name) as source_file:
                            with open(resolved_target, "wb") as output_file:
                                while True:
                                    chunk = source_file.read(65536)
                                    if not chunk:
                                        break
                                    member_bytes += len(chunk)
                                    if member_bytes > MAX_FILE_SIZE_BYTES:
                                        return f"{member_name}: Truncated (decompression exceeded max file size limit)"
                                    output_file.write(chunk)
                except Exception as e:
                    return f"{member_name}: error extracting - {str(e)}"
                return None

            if extract_tasks:
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = {executor.submit(_extract_member, name): name for name in extract_tasks}
                    for future in concurrent.futures.as_completed(futures):
                        err = future.result()
                        if err:
                            skipped.append(err)
    except Exception as e:
        skipped.append(f"Failed to unzip {os.path.basename(str(zip_path))}: {str(e)}")
