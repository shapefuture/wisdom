"""Content identity and attributable binding manifest, without runtime self-modification."""
import hashlib
import json
from pathlib import Path
from . import __version__

def manifest(root=None):
    root=Path(root) if root else Path(__file__).resolve().parents[1]
    files={}
    for base in ["wisdom","architecture","schemas"]:
        for path in sorted((root/base).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix in {".py",".html",".css",".js",".json"}:
                files[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ["pyproject.toml"]:
        files[name]=hashlib.sha256((root/name).read_bytes()).hexdigest()
    identity=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
    return {"schema_version":"1.0.0","generation_id":"sha256:"+identity,"version":__version__,
            "source_hash":identity,"files":files,"bindings":json.loads((root/"architecture/slots.json").read_text()),
            "policy_hash":files["architecture/constitution.json"],"dependency_policy":"Python 3.12+ standard library; no runtime package dependencies",
            "runtime_agentic_profile":"advisory only; external executor disabled",
            "activation":"Manual verified checkout and process restart; no automatic production promotion"}


