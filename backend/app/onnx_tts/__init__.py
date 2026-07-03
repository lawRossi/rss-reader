"""Minimal ONNX TTS runtime for MOSS-TTS-Nano-100M.

Provides OnnxTtsRuntime for voice-cloning TTS inference using onnxruntime.
"""

from .onnx_tts_runtime import OnnxTtsRuntime

__all__ = ["OnnxTtsRuntime"]
