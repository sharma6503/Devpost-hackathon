import json
import logging

logger = logging.getLogger(__name__)


def preprocess_ipynb_content(raw_json: str) -> str:
    """Extracts code and markdown cells from a Jupyter Notebook JSON string.
    Strips outputs and metadata to reduce token usage and improve LLM context.
    Falls back to raw JSON if parsing fails.
    """
    try:
        nb = json.loads(raw_json)
        cells = nb.get("cells", [])
        blocks = []
        for cell in cells:
            ctype = cell.get("cell_type")
            source = "".join(cell.get("source", []))
            if not source.strip():
                continue
            if ctype == "code":
                blocks.append(f"```python\n{source}\n```")
            elif ctype == "markdown":
                blocks.append(source)
        return "\n\n".join(blocks) if blocks else raw_json
    except Exception as e:
        logger.warning(f"preprocess_ipynb_content: malformed notebook JSON, using raw content: {e}")
        return raw_json
