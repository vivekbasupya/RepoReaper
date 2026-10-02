from uuid import uuid4

import pytest
from reporeaper.adapters import FileArtifacts
from reporeaper.domain import ExecutionRequest
from reporeaper.fixtures import manifest, patch_for
from reporeaper.languages import detect


@pytest.mark.parametrize(
    "path,source,name",
    [
        ("a.py", b"def contains(x): return x", "contains"),
        ("a.ts", b"function contains(x: number) { return x; }", "contains"),
        ("a.tsx", b"function View() {return <div/>}", "View"),
        ("a.jsx", b"function View() {return <div/>}", "View"),
        ("a.go", b"package main\nfunc contains(x int) int { return x }", "contains"),
        ("a.java", b"class Example { int contains(int x) { return x; } }", "contains"),
    ],
)
def test_language_registry(path, source, name):
    assert any(symbol["name"] == name for symbol in detect(path).symbols(source))
    assert detect("context.sql") is None


def test_fixture_commit_and_patch_cover_mixed_targets():
    data = manifest("mixed-boundary")
    assert len(data["base_sha"]) == 40
    assert data["base_sha"] == manifest("mixed-boundary")["base_sha"]
    diff = patch_for(data["files"], data["targets"])
    assert "backend/bounds.py" in diff and "frontend/bounds.tsx" in diff
    assert data["targets"][1]["profile"] is None


async def test_artifact_scope_and_traversal(tmp_path):
    store = FileArtifacts(str(tmp_path))
    workspace, other = uuid4(), uuid4()
    key = await store.put(workspace, b"evidence")
    assert await store.get(workspace, key) == b"evidence"
    with pytest.raises(PermissionError):
        await store.get(other, key)
    with pytest.raises(PermissionError):
        await store.get(workspace, f"{workspace}/" + "../" * 20)


def test_execution_contract_rejects_arbitrary_options():
    with pytest.raises(ValueError):
        ExecutionRequest(
            execution_id=uuid4(),
            workspace_id=uuid4(),
            run_id=uuid4(),
            fixture="python-boundary",
            target="python",
            phase="baseline",
            input_hash="a" * 64,
            source_hash="b" * 64,
            docker_options=["--privileged"],
        )
