#!/usr/bin/env python3
"""Download ONNX model assets for MOSS-TTS-Nano voice cloning.

Run this script if the models/ directory is missing or incomplete.
It downloads the TTS and audio codec ONNX models from Hugging Face.

Usage:
    python -m app.onnx_tts.download_models
    python -m app.onnx_tts.download_models --model-dir /path/to/models
"""

from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path
from typing import Sequence

logging.basicConfig(
    format="%(asctime)s %(levelname)s: %(message)s",
    level=logging.INFO,
)

# ── paths (relative to this script) ──

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_DIR = SCRIPT_DIR / "models"

TTS_REPO_ID = "OpenMOSS-Team/MOSS-TTS-Nano-100M-ONNX"
CODEC_REPO_ID = "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX"

MANIFEST_CANDIDATE_RELATIVE_PATHS = (
    "browser_poc_manifest.json",
    "MOSS-TTS-Nano-100M-ONNX/browser_poc_manifest.json",
    "MOSS-TTS-Nano-ONNX-CPU/browser_poc_manifest.json",
)


# ── helpers ──

def _find_manifest_path(model_dir: Path) -> Path | None:
    for relative_path in MANIFEST_CANDIDATE_RELATIVE_PATHS:
        candidate = (model_dir / relative_path).resolve()
        if candidate.is_file():
            return candidate
    return None


def _directory_contains_all(parent: Path, required_names: Sequence[str]) -> bool:
    return all((parent / name).exists() for name in required_names)


def _find_directory_with_required_names(root_dir: Path, required_names: Sequence[str]) -> Path | None:
    if not root_dir.exists():
        return None
    if _directory_contains_all(root_dir, required_names):
        return root_dir
    sentinel_name = str(required_names[0])
    for candidate in root_dir.rglob(sentinel_name):
        parent = candidate.parent
        if _directory_contains_all(parent, required_names):
            return parent
    return None


def _promote_directory_contents(source_dir: Path, target_dir: Path) -> None:
    """Move all files from source_dir into target_dir (flat merge)."""
    if source_dir.resolve() == target_dir.resolve():
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    for child in source_dir.iterdir():
        destination = target_dir / child.name
        if destination.exists():
            continue
        shutil.move(str(child), str(destination))


def _normalize_download_layout(target_dir: Path, required_names: Sequence[str]) -> None:
    """After download, files may be in a subdirectory — promote them up."""
    candidate_dir = _find_directory_with_required_names(target_dir, required_names)
    if candidate_dir is None:
        return
    _promote_directory_contents(candidate_dir, target_dir)


def _download_repo(*, repo_id: str, local_dir: Path, allow_patterns: Sequence[str]) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "huggingface_hub is required to download model assets. "
            "Install it with: pip install huggingface_hub"
        ) from exc
    local_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(local_dir),
        local_dir_use_symlinks=False,
        allow_patterns=list(allow_patterns),
    )


# ── main ──

def ensure_model_dir(model_dir: Path | None = None) -> Path:
    """Download models if not present. Returns the model directory path."""
    resolved = (model_dir or DEFAULT_MODEL_DIR).expanduser().resolve()

    # Check if models already exist
    manifest_path = _find_manifest_path(resolved)
    if manifest_path is not None:
        logging.info("Models already present at %s", resolved)
        return resolved

    logging.info("Models not found at %s — downloading from Hugging Face...", resolved)
    logging.info("  TTS model:   %s", TTS_REPO_ID)
    logging.info("  Codec model: %s", CODEC_REPO_ID)

    # Download TTS model
    tts_dir = resolved / "MOSS-TTS-Nano-100M-ONNX"
    logging.info("Downloading TTS model to %s ...", tts_dir)
    _download_repo(
        repo_id=TTS_REPO_ID,
        local_dir=tts_dir,
        allow_patterns=("*.onnx", "*.data", "*.json", "tokenizer.model"),
    )
    _normalize_download_layout(
        tts_dir,
        required_names=("browser_poc_manifest.json", "tts_browser_onnx_meta.json", "tokenizer.model"),
    )

    # Download audio codec model
    codec_dir = resolved / "MOSS-Audio-Tokenizer-Nano-ONNX"
    logging.info("Downloading codec model to %s ...", codec_dir)
    _download_repo(
        repo_id=CODEC_REPO_ID,
        local_dir=codec_dir,
        allow_patterns=("*.onnx", "*.data", "*.json"),
    )
    _normalize_download_layout(
        codec_dir,
        required_names=("codec_browser_onnx_meta.json",),
    )

    # Final verification
    manifest_path = _find_manifest_path(resolved)
    if manifest_path is None:
        raise FileNotFoundError(
            "Models were downloaded but browser_poc_manifest.json is still missing. "
            "The download may have failed or the repository layout has changed."
        )

    logging.info("Download complete! Models are ready at %s", resolved)
    return resolved


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download ONNX model assets for MOSS-TTS-Nano voice cloning.",
    )
    parser.add_argument(
        "--model-dir",
        default=None,
        help=f"Target directory for models. Default: {DEFAULT_MODEL_DIR}",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    model_dir = Path(args.model_dir) if args.model_dir else None
    ensure_model_dir(model_dir)


if __name__ == "__main__":
    main()
