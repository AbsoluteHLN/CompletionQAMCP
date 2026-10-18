"""Trusted command: parse files, never import or execute reviewed source."""
import ast
import json
import sys
from pathlib import Path

failed = False
for filename in sys.argv[1:]:
    p = Path(filename)
    try:
        text = p.read_text(encoding="utf-8")
        if p.suffix == ".py":
            ast.parse(text, filename=p.name)
        elif p.suffix == ".json":
            json.loads(text)
        else:
            raise ValueError("Unsupported file extension")
        print(json.dumps({"file": p.name, "status": "pass"}))
    except Exception as exc:
        failed = True
        print(json.dumps({"file": p.name, "status": "fail", "error": str(exc)}))
sys.exit(1 if failed else 0)
