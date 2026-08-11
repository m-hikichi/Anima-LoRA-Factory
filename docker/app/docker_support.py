from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable


MODEL_EXTENSIONS = {".bin", ".ckpt", ".pt", ".pth", ".safetensors"}
OUTPUT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class PathAccessError(ValueError):
    pass


def configured_roots() -> dict[str, Path]:
    return {
        "datasets": Path(os.environ.get("DATASETS_ROOT", "/workspace/datasets")).resolve(),
        "models": Path(os.environ.get("MODELS_ROOT", "/workspace/models")).resolve(),
        "output": Path(os.environ.get("OUTPUT_ROOT", "/workspace/output")).resolve(),
    }


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate_path(
    raw_path: str,
    allowed_roots: Iterable[str],
    expected: str = "any",
    must_exist: bool = True,
) -> str:
    if not raw_path or not raw_path.strip():
        raise PathAccessError("Path is required")

    roots = configured_roots()
    try:
        allowed = [roots[name] for name in allowed_roots]
    except KeyError as exc:
        raise PathAccessError(f"Unknown mount root: {exc.args[0]}") from exc

    candidate = Path(raw_path).expanduser().resolve(strict=False)
    if not any(_is_relative_to(candidate, root) for root in allowed):
        raise PathAccessError("Path is outside the configured Docker mounts")
    if must_exist and not candidate.exists():
        raise PathAccessError("Path does not exist")
    if expected == "file" and candidate.exists() and not candidate.is_file():
        raise PathAccessError("Expected a file path")
    if expected == "directory" and candidate.exists() and not candidate.is_dir():
        raise PathAccessError("Expected a directory path")
    return str(candidate)


def validate_output_name(name: str) -> str:
    if not OUTPUT_NAME_PATTERN.fullmatch(name or ""):
        raise PathAccessError(
            "Output name must contain only letters, numbers, dots, underscores, and hyphens"
        )
    return name


def validate_training_config(config) -> None:
    config.path = validate_path(config.path, ("datasets",), "directory")
    config.model = validate_path(config.model, ("models",), "file")
    config.vae = validate_path(config.vae, ("models",), "file")
    config.qwen3 = validate_path(config.qwen3, ("models",), "file")
    config.output_dir = validate_path(config.output_dir, ("output",), "directory")
    validate_output_name(config.name)
    if config.shutdown:
        raise PathAccessError("Host shutdown is unavailable in Docker mode")


def get_mixed_precision() -> str:
    requested = os.environ.get("MIXED_PRECISION", "auto").strip().lower()
    if requested in {"fp16", "bf16"}:
        return requested
    if requested != "auto":
        raise ValueError("MIXED_PRECISION must be auto, fp16, or bf16")

    try:
        import torch

        if torch.cuda.is_available():
            major, _minor = torch.cuda.get_device_capability()
            return "bf16" if major >= 8 and torch.cuda.is_bf16_supported() else "fp16"
    except Exception:
        pass
    return "fp16"


def list_entries(root_name: str, raw_path: str | None, kind: str) -> dict:
    roots = configured_roots()
    if root_name not in roots:
        raise PathAccessError("Unknown mount root")
    if kind not in {"directory", "model"}:
        raise PathAccessError("Unknown browser kind")

    root = roots[root_name]
    current = validate_path(raw_path or str(root), (root_name,), "directory")
    current_path = Path(current)
    entries = []
    try:
        children = sorted(current_path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    except OSError as exc:
        raise PathAccessError(f"Unable to read directory: {exc}") from exc

    for child in children:
        resolved = child.resolve(strict=False)
        if not _is_relative_to(resolved, root):
            continue
        if child.is_dir():
            entries.append({"name": child.name, "path": str(resolved), "type": "directory"})
        elif kind == "model" and child.suffix.lower() in MODEL_EXTENSIONS:
            entries.append({"name": child.name, "path": str(resolved), "type": "file"})

    parent = None if current_path == root else str(current_path.parent)
    return {
        "root": root_name,
        "path": str(current_path),
        "parent": parent,
        "entries": entries,
    }


def runtime_info() -> dict:
    gpu = {"available": False, "name": None, "capability": None}
    try:
        import torch

        if torch.cuda.is_available():
            capability = torch.cuda.get_device_capability()
            gpu = {
                "available": True,
                "name": torch.cuda.get_device_name(0),
                "capability": f"{capability[0]}.{capability[1]}",
            }
    except Exception as exc:
        gpu["error"] = str(exc)

    return {
        "docker": os.environ.get("ANIMA_DOCKER") == "1",
        "precision": get_mixed_precision(),
        "gpu": gpu,
        "roots": {name: str(path) for name, path in configured_roots().items()},
    }


def register_routes(app) -> None:
    from fastapi import HTTPException, Query

    @app.get("/api/health")
    async def docker_health():
        return {"status": "ok"}

    @app.get("/api/runtime-info")
    async def docker_runtime_info():
        return runtime_info()

    @app.get("/api/files")
    async def docker_files(
        root: str = Query(...),
        path: str | None = Query(None),
        kind: str = Query("directory"),
    ):
        try:
            return list_entries(root, path, kind)
        except PathAccessError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

