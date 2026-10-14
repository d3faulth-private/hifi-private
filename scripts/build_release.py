"""Build a source ZIP plus a no-install Python zipapp, using only the stdlib."""
from pathlib import Path
import hashlib
import shutil
import sys
import tempfile
import zipapp
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hifi import __version__


def main():
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    app = output / "hifi.pyz"
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        shutil.copytree(ROOT / "hifi", dest / "hifi", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for name in ["LICENSE", "CREDITS.md"]:
            shutil.copy2(ROOT / name, dest / name)
        shutil.copytree(ROOT / "LICENSES", dest / "LICENSES")
        zipapp.create_archive(dest, app, interpreter="/usr/bin/env python3", main="hifi.cli:main", compressed=True)
    selected = [ROOT / name for name in ["README.md", "LICENSE", "CREDITS.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md", "pyproject.toml", ".gitignore"]]
    for folder, patterns in {"hifi": ["*.py", "UPSTREAM.json"], "tests": ["*.py", "*.json"], "scripts": ["*.py"], "docs": ["*.md", "*.svg"], "LICENSES": ["*.txt"], ".github": ["*.yml"]}.items():
        for pattern in patterns:
            selected.extend((ROOT / folder).rglob(pattern))
    prefix = f"D3FAULTH-HIFI-v{__version__}"
    archive = output / f"{prefix}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(selected):
            z.write(path, f"{prefix}/{path.relative_to(ROOT)}")
        z.write(app, f"{prefix}/hifi.pyz")
    hashes = output / "SHA256SUMS"
    hashes.write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in [archive, app]))
    print(archive)
    print(app)
    print(hashes)


if __name__ == "__main__":
    main()
