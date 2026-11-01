"""Configuration management for Frognano Execution Harness."""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class HarnessConfig:
    """Runtime and environment configuration for the harness."""

    endpoint: str = "http://127.0.0.1:8080/v1"
    model_alias: str = "frognano"
    context_limit: int = 65536
    max_retries: int = 2
    test_timeout_sec: int = 120
    approval_timeout_sec: int = 60
    request_timeout_sec: int = 180
    project_root: str = "."
    harness_dir_name: str = ".harness"

    @property
    def root_path(self) -> Path:
        return Path(self.project_root).resolve()

    @property
    def model_endpoint(self) -> str:
        return self.endpoint

    @property
    def context_token_budget(self) -> int:
        return self.context_limit

    @property
    def harness_path(self) -> Path:
        return (self.root_path / self.harness_dir_name).resolve()

    @property
    def db_path(self) -> Path:
        return self.harness_path / "state.db"

    @property
    def logs_path(self) -> Path:
        return self.harness_path / "logs"

    @property
    def reports_path(self) -> Path:
        return self.harness_path / "reports"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HarnessConfig":
        return cls(
            endpoint=str(data.get("endpoint", "http://127.0.0.1:8080/v1")),
            model_alias=str(data.get("model_alias", "frognano")),
            context_limit=int(data.get("context_limit", 65536)),
            max_retries=int(data.get("max_retries", 2)),
            test_timeout_sec=int(data.get("test_timeout_sec", 120)),
            approval_timeout_sec=int(data.get("approval_timeout_sec", 60)),
            request_timeout_sec=int(data.get("request_timeout_sec", 180)),
            project_root=str(data.get("project_root", ".")),
            harness_dir_name=str(data.get("harness_dir_name", ".harness")),
        )


def load_config(project_root: Optional[Path] = None) -> HarnessConfig:
    """Load configuration from .harness/config.json with environment variable overrides."""
    root = (project_root or Path.cwd()).resolve()
    config_file = root / ".harness" / "config.json"
    data: dict[str, Any] = {"project_root": str(root)}

    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception:
            pass

    # Environment variable overrides
    if "FROGNANO_ENDPOINT" in os.environ:
        data["endpoint"] = os.environ["FROGNANO_ENDPOINT"]
    if "FROGNANO_MODEL" in os.environ:
        data["model_alias"] = os.environ["FROGNANO_MODEL"]
    if "FROGNANO_CONTEXT_LIMIT" in os.environ:
        data["context_limit"] = int(os.environ["FROGNANO_CONTEXT_LIMIT"])
    if "FROGNANO_MAX_RETRIES" in os.environ:
        data["max_retries"] = int(os.environ["FROGNANO_MAX_RETRIES"])

    return HarnessConfig.from_dict(data)


def save_config(config: HarnessConfig) -> Path:
    """Save configuration to .harness/config.json."""
    config.harness_path.mkdir(parents=True, exist_ok=True)
    config_file = config.harness_path / "config.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)
    return config_file
