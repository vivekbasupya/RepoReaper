from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Outcome(StrEnum):
    VERIFIED = "verified_fix"
    PARTIAL = "partial_verification"
    UNVERIFIED = "unverified_patch"
    NOT_REPRODUCED = "not_reproduced"
    ENVIRONMENT = "environment_failure"
    CANCELLED = "cancelled"


class RunStatus(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    INVESTIGATING = "investigating"
    WAITING_EXECUTION = "waiting_execution"
    WAITING_INPUT = "waiting_input"
    VERIFYING = "verifying"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExecutionRequest(Contract):
    schema_version: int = Field(default=1, ge=1, le=1)
    execution_id: UUID
    workspace_id: UUID
    run_id: UUID
    fixture: str
    target: str
    phase: str
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    patch_hash: str | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    profile_version: str = "1"
    image_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")


class ExecutionResult(Contract):
    schema_version: int = 1
    execution_id: UUID
    status: str
    exit_code: int | None = None
    expected_failure: bool = False
    log: str = ""
    log_artifact_id: UUID | None = None
    log_sha256: str = ""
    duration_seconds: float = 0
    image_digest: str = ""
    source_hash: str = ""
    patch_hash: str | None = None
    harness_hash: str = ""
    toolchain: str = ""
    result_version: int = 1
    cleaned: bool = False


class RunCreate(Contract):
    fixture: str = "python-boundary"
    title: str = Field(
        default="Inclusive boundary excludes the maximum", min_length=1, max_length=200
    )
    description: str = Field(default="The upper boundary should be included.", max_length=8000)
    fault: str | None = None


class RunView(Contract):
    id: UUID
    fixture: str
    title: str
    status: RunStatus
    outcome: Outcome | None
    base_sha: str
    version: int
    graph_version: str
    latest_sequence: int
    patch: str | None
    patch_sha256: str | None
    evidence: list[dict[str, Any]]
    targets: list[dict[str, Any]]
    mode: str = "deterministic_fixture"
    error: str | None = None


class ErrorEnvelope(Contract):
    code: str
    message: str
    retryable: bool
    correlation_id: str


class ModelAdapter(Protocol):
    async def propose(
        self, fixture: str, files: dict[str, str], targets: list[dict[str, Any]]
    ) -> str: ...


class EmbeddingAdapter(Protocol):
    version: str
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class ArtifactStore(Protocol):
    async def put(self, workspace_id: UUID, content: bytes) -> str: ...
    async def get(self, workspace_id: UUID, key: str) -> bytes: ...


class RepositoryProvider(Protocol):
    async def snapshot(self, locator: str, revision: str) -> dict[str, Any]: ...


class SandboxProvider(Protocol):
    async def submit(self, request: ExecutionRequest) -> ExecutionResult: ...
    async def status(self, execution_id: UUID) -> ExecutionResult: ...
    async def cancel(self, execution_id: UUID) -> ExecutionResult: ...


class LanguageAdapter(Protocol):
    name: str
    extensions: tuple[str, ...]

    def symbols(self, source: bytes) -> list[dict[str, Any]]: ...


class ExecutionProfile(Contract):
    id: str
    version: str
    language: str
    image: str
    argv: list[str]
    memory_mb: int = 256
    pids: int = 64
