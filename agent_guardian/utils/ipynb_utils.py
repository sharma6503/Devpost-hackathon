import json
import logging

logger = logging.getLogger(__name__)


def preprocess_ipynb_content(raw_json: str, max_chars: int = 500_000) -> str:
    """Extracts code and markdown cells from a Jupyter Notebook JSON string.
    Strips outputs and metadata to reduce token usage and improve LLM context.
    Falls back to raw JSON if parsing fails.
    """
    try:
        nb = json.loads(raw_json)
        cells = nb.get("cells", [])
        blocks = []
        total_len = 0
        for cell in cells:
            ctype = cell.get("cell_type")
            source = "".join(cell.get("source", []))
            if not source.strip():
                continue
            if ctype == "code":
                block = f"```python\n{source}\n```"
            elif ctype == "markdown":
                block = source
            else:
                continue

            if total_len + len(block) > max_chars:
                blocks.append("\n[TRUNCATED: Additional notebook cells omitted to stay within limits]")
                break
            blocks.append(block)
            total_len += len(block)
        return "\n\n".join(blocks) if blocks else raw_json[:max_chars]
    except Exception as e:
        logger.warning(f"preprocess_ipynb_content: malformed notebook JSON, using raw content: {e}")
        return raw_json[:max_chars]
