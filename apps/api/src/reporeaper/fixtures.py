"""Trusted fixture metadata. CPU hashing occurs during seeding/indexing, never in API routes."""

import difflib
import hashlib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "fixtures" / "repositories"
CATALOG = {
    "python-boundary": [("python", ".", "bounds.py", "python")],
    "typescript-boundary": [("typescript", ".", "bounds.ts", "node")],
    "mixed-boundary": [
        ("python", "backend", "backend/bounds.py", "python"),
        ("tsx", "frontend", "frontend/bounds.tsx", None),
    ],
}


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def git_object(kind: str, content: bytes) -> bytes:
    return hashlib.sha1(f"{kind} {len(content)}\0".encode() + content).digest()


def git_tree(root: Path) -> bytes:
    entries = []
    for path in sorted(root.iterdir(), key=lambda p: p.name + ("/" if p.is_dir() else "")):
        if path.is_dir():
            mode, digest = "40000", git_tree(path)
        else:
            mode, digest = "100644", git_object("blob", path.read_bytes())
        entries.append(f"{mode} {path.name}\0".encode() + digest)
    return git_object("tree", b"".join(entries))


def manifest(fixture: str) -> dict[str, Any]:
    root = FIXTURES / fixture
    tree = git_tree(root).hex()
    commit = (
        f"tree {tree}\nauthor RepoReaper <fixture@localhost> 0 +0000\n"
        "committer RepoReaper <fixture@localhost> 0 +0000\n\nCurated boundary fixture\n"
    )
    files = {p.relative_to(root).as_posix(): p.read_text() for p in root.rglob("*") if p.is_file()}
    return {
        "base_sha": git_object("commit", commit.encode()).hex(),
        "files": files,
        "targets": [
            {
                "id": language,
                "root": package,
                "path": path,
                "profile": profile,
                "analysis": "syntax",
                "verification": "available" if profile else "missing_profile",
            }
            for language, package, path, profile in CATALOG[fixture]
        ],
    }


def patch_for(files: dict[str, str], targets: list[dict]) -> str:
    chunks = []
    for target in targets:
        path = target["path"]
        original = files[path]
        patched = original.replace("< maximum", "<= maximum")
        chunks.extend(
            difflib.unified_diff(
                original.splitlines(True),
                patched.splitlines(True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
    return "".join(chunks)


class DeterministicModel:
    async def propose(
        self, fixture: str, files: dict[str, str], targets: list[dict[str, Any]]
    ) -> str:
        # Known curated bug only. No claims about arbitrary repository repair.
        if fixture not in CATALOG:
            raise ValueError("The deterministic adapter accepts curated fixtures only")
        return patch_for(files, targets)
