import json

def _parse_json_response(text: str) -> dict:
    """Parse JSON from Gemini response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    text = text.strip()
    # Robust fallback just in case
    if text.startswith("{"):
        try:
            return json.loads(text)
        except Exception as e:
            pass
            
    # ultra robust fallback
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end+1]
        return json.loads(text)
    return json.loads(text)

raw1 = """
Here is the JSON you requested:
```json
{
  "subject": "hello",
  "body": "world"
}
```
"""

print(_parse_json_response(raw1))
