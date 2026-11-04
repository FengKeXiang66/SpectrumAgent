"""All mutable runtime data lives under the per-user application data root."""

import os
from dataclasses import dataclass
from pathlib import Path

# Reserved configuration locations; no NAS access or guard in this milestone.
NAS_SOURCE_ROOT: Path | None = None
NAS_OUTPUT_ROOT: Path | None = None


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @classmethod
    def from_environment(cls) -> "AppPaths":
        local = Path(os.environ["LOCALAPPDATA"])
        if not local.is_absolute():
            raise ValueError("LOCALAPPDATA must be an absolute path")
        return cls(local / "SpectrumAgent")

    @property
    def run(self) -> Path:
        return self.root / "run"

    @property
    def handshake(self) -> Path:
        return self.run / "handshake.json"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def testdata(self) -> Path:
        return self.root / "testdata"

    @property
    def database(self) -> Path:
        return self.root / "db" / "spectrum-agent.sqlite3"

    @property
    def snapshots(self) -> Path:
        return self.root / "annotations"

    @property
    def preprocessed(self) -> Path:
        return self.root / "preprocessed"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def trash(self) -> Path:
        return self.root / "trash"

    def create_directories(self) -> None:
        from spectrumagent.storage.guard import initialize, validate_bootstrap
        validate_bootstrap(self)
        # Explicit bootstrap exception: create trash before the storage self-check.
        for directory in (self.run, self.logs, self.testdata, self.database.parent, self.exports, self.trash):
            directory.mkdir(parents=True, exist_ok=True)
        initialize(self)
