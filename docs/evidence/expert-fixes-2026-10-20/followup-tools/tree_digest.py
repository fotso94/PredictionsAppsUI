"""The app tree digest of a checkout, reimplemented from source_identity's docstring with the standard library."""
import hashlib, os, sys
from pathlib import Path
root = Path(sys.argv[1]) / "backend" / "app"
rel = []
for folder, folders, files in os.walk(root):
    folders[:] = [n for n in folders if n != "__pycache__"]
    rel.extend(Path(folder, n).relative_to(root).as_posix() for n in files if n.endswith(".py"))
d = hashlib.sha256()
for p in sorted(rel):
    d.update(p.encode()); d.update(b"\0"); d.update((root / p).read_bytes()); d.update(b"\0")
print(d.hexdigest(), len(rel))
