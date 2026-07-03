"""Minimal ONNX CPU runtime for MOSS-TTS-Nano-100M voice cloning.

Stripped-down version of the original ort_cpu_runtime — removes CUDA,
streaming decode, and full/host-sampled sampling modes. Only CPU execution
with greedy and fixed-sampled frame generation is kept.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import onnxruntime as ort

SAMPLE_MODE_GREEDY = "greedy"
SAMPLE_MODE_FIXED = "fixed"
EXECUTION_PROVIDER_CPU = "cpu"

MANIFEST_CANDIDATE_RELATIVE_PATHS = (
    "browser_poc_manifest.json",
    "MOSS-TTS-Nano-100M-ONNX/browser_poc_manifest.json",
    "MOSS-TTS-Nano-ONNX-CPU/browser_poc_manifest.json",
)


def _argmax(values: np.ndarray) -> int:
    return int(np.argmax(values))


def _normalize_sample_mode(raw_sample_mode: str | None, raw_do_sample: bool = True) -> str:
    normalized = str(raw_sample_mode or "").strip()
    if normalized in {SAMPLE_MODE_GREEDY, SAMPLE_MODE_FIXED}:
        return normalized
    return SAMPLE_MODE_FIXED if raw_do_sample else SAMPLE_MODE_GREEDY


def _flatten3d_int32(nested: list[list[list[int]]]) -> tuple[np.ndarray, list[int]]:
    dim0 = len(nested)
    dim1 = len(nested[0])
    dim2 = len(nested[0][0])
    data = np.zeros((dim0 * dim1 * dim2,), dtype=np.int32)
    offset = 0
    for i in range(dim0):
        for j in range(dim1):
            for k in range(dim2):
                data[offset] = int(nested[i][j][k])
                offset += 1
    return data, [dim0, dim1, dim2]


def _flatten2d_int32(nested: list[list[int]]) -> tuple[np.ndarray, list[int]]:
    dim0 = len(nested)
    dim1 = len(nested[0])
    data = np.zeros((dim0 * dim1,), dtype=np.int32)
    offset = 0
    for i in range(dim0):
        for j in range(dim1):
            data[offset] = int(nested[i][j])
            offset += 1
    return data, [dim0, dim1]


def _slice_channel_major_audio(audio: np.ndarray, start_sample: int = 0, end_sample: int | None = None) -> list[np.ndarray]:
    if audio.ndim != 3 or audio.shape[0] != 1:
        raise ValueError(f"Unexpected audio tensor shape: {audio.shape}")
    channels = int(audio.shape[1])
    total_samples = int(audio.shape[2])
    start = max(0, int(start_sample))
    end = total_samples if end_sample is None else max(start, min(int(end_sample), total_samples))
    return [audio[0, channel_index, start:end].astype(np.float32, copy=False) for channel_index in range(channels)]


def _extract_last_hidden(hidden_states: np.ndarray) -> np.ndarray:
    if hidden_states.ndim == 2:
        return hidden_states.astype(np.float32, copy=False)
    if hidden_states.ndim != 3 or hidden_states.shape[0] != 1:
        raise ValueError(f"Unexpected global_hidden shape: {hidden_states.shape}")
    return hidden_states[:, -1, :].astype(np.float32, copy=False)


def _apply_repetition_penalty(values: np.ndarray, previous_token_ids: list[int], repetition_penalty: float) -> np.ndarray:
    if not previous_token_ids or repetition_penalty == 1.0:
        return values
    result = values.copy()
    for token_id in set(int(item) for item in previous_token_ids):
        if token_id < 0 or token_id >= result.shape[0]:
            continue
        result[token_id] = result[token_id] * repetition_penalty if result[token_id] < 0 else result[token_id] / repetition_penalty
    return result


def _argmax_with_repetition_penalty(values: np.ndarray, previous_token_set: set[int], repetition_penalty: float) -> int:
    best_index = 0
    best_value = float("-inf")
    apply_penalty = bool(previous_token_set) and repetition_penalty != 1.0
    for index, value in enumerate(values):
        score = float(value)
        if apply_penalty and index in previous_token_set:
            score = score * repetition_penalty if score < 0 else score / repetition_penalty
        if score > best_value:
            best_value = score
            best_index = index
    return int(best_index)


def _softmax(values: np.ndarray) -> np.ndarray:
    max_value = float(np.max(values))
    shifted = np.asarray(values - max_value, dtype=np.float64)
    exps = np.exp(shifted)
    return exps / np.sum(exps, dtype=np.float64)


def _sample_from_scores(
    values: np.ndarray,
    *,
    do_sample: bool,
    temperature: float,
    top_k: int,
    top_p: float,
    rng: np.random.Generator,
) -> int:
    if not do_sample:
        return _argmax(values)
    if not (temperature > 0):
        raise ValueError("temperature must be positive when do_sample=True")
    scores = np.asarray(values, dtype=np.float32).copy() / float(temperature)
    if top_k > 0 and top_k < scores.shape[0]:
        sorted_desc = np.sort(scores)[::-1]
        threshold = float(sorted_desc[top_k - 1])
        scores[scores < threshold] = float("-inf")
    if top_p > 0 and top_p < 1:
        indexed = list(enumerate(scores.tolist()))
        indexed.sort(key=lambda item: item[1], reverse=True)
        sorted_scores = np.asarray([item[1] for item in indexed], dtype=np.float32)
        sorted_probs = _softmax(sorted_scores)
        remove_mask = [False] * len(indexed)
        cumulative = 0.0
        for index, probability in enumerate(sorted_probs):
            cumulative += float(probability)
            if cumulative > float(top_p):
                remove_mask[index] = True
        for index in range(len(remove_mask) - 1, 0, -1):
            remove_mask[index] = remove_mask[index - 1]
        if remove_mask:
            remove_mask[0] = False
        for index, should_remove in enumerate(remove_mask):
            if should_remove:
                scores[indexed[index][0]] = float("-inf")
    probabilities = _softmax(scores)
    random_value = float(rng.random())
    for index, probability in enumerate(probabilities):
        random_value -= float(probability)
        if random_value <= 0:
            return int(index)
    return _argmax(scores)


def _sample_assistant_text_token(
    text_logits: np.ndarray,
    manifest: dict[str, Any],
    generation_defaults: dict[str, Any],
    rng: np.random.Generator,
) -> int:
    candidate_ids = np.asarray(
        [
            int(manifest["tts_config"]["audio_assistant_slot_token_id"]),
            int(manifest["tts_config"]["audio_end_token_id"]),
        ],
        dtype=np.int32,
    )
    candidate_scores = text_logits[candidate_ids]
    sampled_index = _sample_from_scores(
        candidate_scores,
        do_sample=bool(generation_defaults["do_sample"]),
        temperature=float(generation_defaults["text_temperature"]),
        top_k=min(int(generation_defaults["text_top_k"]), int(candidate_scores.shape[0])),
        top_p=float(generation_defaults["text_top_p"]),
        rng=rng,
    )
    return int(candidate_ids[sampled_index])


def _sample_audio_token(
    audio_logits: np.ndarray,
    previous_token_ids: list[int],
    previous_token_set: set[int],
    generation_defaults: dict[str, Any],
    rng: np.random.Generator,
) -> int:
    repetition_penalty = float(generation_defaults["audio_repetition_penalty"])
    if not bool(generation_defaults["do_sample"]):
        return _argmax_with_repetition_penalty(audio_logits, previous_token_set, repetition_penalty)
    penalized_scores = _apply_repetition_penalty(audio_logits, previous_token_ids, repetition_penalty)
    return _sample_from_scores(
        penalized_scores,
        do_sample=True,
        temperature=float(generation_defaults["audio_temperature"]),
        top_k=int(generation_defaults["audio_top_k"]),
        top_p=float(generation_defaults["audio_top_p"]),
        rng=rng,
    )


class OrtCpuRuntime:
    """Minimal ONNX CPU runtime for MOSS-TTS-Nano voice cloning inference."""

    def __init__(
        self,
        model_dir: str | Path,
        thread_count: int = 4,
        max_new_frames: int | None = None,
        do_sample: bool | None = None,
        sample_mode: str | None = None,
    ) -> None:
        self.model_dir = Path(model_dir).expanduser().resolve()
        self.thread_count = max(1, int(thread_count))
        self.ort_providers = ["CPUExecutionProvider"]
        self.manifest_path = self._resolve_manifest_path(self.model_dir)
        self.manifest_dir = self.manifest_path.parent
        manifest: dict[str, Any] = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.manifest = manifest
        if max_new_frames is not None:
            self.manifest["generation_defaults"]["max_new_frames"] = int(max_new_frames)
        if do_sample is not None:
            self.manifest["generation_defaults"]["do_sample"] = bool(do_sample)
        self.manifest["generation_defaults"]["sample_mode"] = _normalize_sample_mode(
            sample_mode if sample_mode is not None else self.manifest["generation_defaults"].get("sample_mode"),
            bool(self.manifest["generation_defaults"]["do_sample"]),
        )
        self.manifest["generation_defaults"]["do_sample"] = (
            self.manifest["generation_defaults"]["sample_mode"] != SAMPLE_MODE_GREEDY
        )
        self.tts_meta_path = self.resolve_manifest_relative_path(manifest["model_files"]["tts_meta"])
        self.codec_meta_path = self.resolve_manifest_relative_path(manifest["model_files"]["codec_meta"])
        self.tts_meta: dict[str, Any] = json.loads(self.tts_meta_path.read_text(encoding="utf-8"))
        self.codec_meta: dict[str, Any] = json.loads(self.codec_meta_path.read_text(encoding="utf-8"))
        self.rng = np.random.default_rng(1234)
        self.sessions = self._create_sessions()

    @property
    def execution_provider(self) -> str:
        return EXECUTION_PROVIDER_CPU

    # ── path resolution ──

    def _resolve_manifest_path(self, model_dir: Path) -> Path:
        for relative_path in MANIFEST_CANDIDATE_RELATIVE_PATHS:
            candidate = (model_dir / relative_path).resolve()
            if candidate.is_file():
                return candidate
        raise FileNotFoundError(
            f"browser_poc_manifest.json not found under {model_dir}. "
            f"tried: {', '.join(str((model_dir / p).resolve()) for p in MANIFEST_CANDIDATE_RELATIVE_PATHS)}"
        )

    def resolve_manifest_relative_path(self, relative_path: str) -> Path:
        return (self.manifest_dir / relative_path).resolve()

    # ── session creation ──

    def _create_ort_session(self, onnx_path: str | Path) -> ort.InferenceSession:
        options = ort.SessionOptions()
        options.intra_op_num_threads = self.thread_count
        options.inter_op_num_threads = self.thread_count
        return ort.InferenceSession(
            str(onnx_path),
            sess_options=options,
            providers=self.ort_providers,
        )

    def _create_sessions(self) -> dict[str, ort.InferenceSession]:
        tts_dir = self.tts_meta_path.parent
        codec_dir = self.codec_meta_path.parent

        tts_files = self.tts_meta.get("files", {})
        codec_files = self.codec_meta.get("files", {})

        sessions: dict[str, ort.InferenceSession] = {}
        sessions["prefill"] = self._create_ort_session(tts_dir / tts_files["prefill"])
        sessions["decode"] = self._create_ort_session(tts_dir / tts_files["decode_step"])
        sessions["local_decoder"] = self._create_ort_session(tts_dir / tts_files["local_decoder"])

        # Optional: local_greedy_frame
        if tts_files.get("local_greedy_frame"):
            sessions["local_greedy_frame"] = self._create_ort_session(tts_dir / tts_files["local_greedy_frame"])
        # Optional: local_fixed_sampled_frame
        if tts_files.get("local_fixed_sampled_frame"):
            sessions["local_fixed_sampled_frame"] = self._create_ort_session(tts_dir / tts_files["local_fixed_sampled_frame"])

        sessions["codec_encode"] = self._create_ort_session(codec_dir / codec_files["encode"])
        sessions["codec_decode"] = self._create_ort_session(codec_dir / codec_files["decode_full"])

        return sessions

    # ── builtin voices ──

    def list_builtin_voices(self) -> list[dict[str, Any]]:
        return list(self.manifest.get("builtin_voices", []))

    # ── request building ──

    def build_text_rows(self, token_ids: list[int]) -> list[list[int]]:
        rows: list[list[int]] = []
        row_width = int(self.manifest["tts_config"]["n_vq"]) + 1
        for token_id in token_ids:
            row = [int(self.manifest["tts_config"]["audio_pad_token_id"])] * row_width
            row[0] = int(token_id)
            rows.append(row)
        return rows

    def build_audio_prefix_rows(
        self, prompt_audio_codes: list[list[int]], slot_token_id: int | None = None
    ) -> list[list[int]]:
        rows: list[list[int]] = []
        row_width = int(self.manifest["tts_config"]["n_vq"]) + 1
        resolved_slot_token_id = int(
            self.manifest["tts_config"]["audio_user_slot_token_id"]
            if slot_token_id is None
            else slot_token_id
        )
        for code_row in prompt_audio_codes:
            row = [int(self.manifest["tts_config"]["audio_pad_token_id"])] * row_width
            row[0] = resolved_slot_token_id
            for idx in range(min(len(code_row), int(self.manifest["tts_config"]["n_vq"]))):
                row[idx + 1] = int(code_row[idx])
            rows.append(row)
        return rows

    def build_voice_clone_request_rows(
        self,
        prompt_audio_codes: list[list[int]],
        text_token_ids: list[int],
    ) -> dict[str, list[list[int]]]:
        prefix_text_token_ids = [
            *self.manifest["prompt_templates"]["user_prompt_prefix_token_ids"],
            int(self.manifest["tts_config"]["audio_start_token_id"]),
        ]
        suffix_text_token_ids = [
            int(self.manifest["tts_config"]["audio_end_token_id"]),
            *self.manifest["prompt_templates"]["user_prompt_after_reference_token_ids"],
            *text_token_ids,
            *self.manifest["prompt_templates"]["assistant_prompt_prefix_token_ids"],
            int(self.manifest["tts_config"]["audio_start_token_id"]),
        ]
        rows = [
            *self.build_text_rows(prefix_text_token_ids),
            *self.build_audio_prefix_rows(prompt_audio_codes),
            *self.build_text_rows(suffix_text_token_ids),
        ]
        return {
            "inputIds": rows,
            "attentionMask": [[1 for _ in rows]],
        }

    def create_empty_local_cached_past(self) -> dict[str, np.ndarray]:
        local_layers = int(self.tts_meta["model_config"]["local_layers"])
        local_heads = int(self.tts_meta["model_config"]["local_heads"])
        local_head_dim = int(self.tts_meta["model_config"]["local_head_dim"])
        return {
            name: np.zeros((1, 0, local_heads, local_head_dim), dtype=np.float32)
            for layer_index in range(local_layers)
            for name in (f"local_past_key_{layer_index}", f"local_past_value_{layer_index}")
        }

    # ── local frame generation ──

    def run_local_greedy_frame(
        self,
        global_hidden: np.ndarray,
        *,
        previous_token_sets_by_channel: list[set[int]],
        repetition_penalty: float,
    ) -> tuple[bool, list[int]]:
        audio_codebook_size = int(self.tts_meta["model_config"]["audio_codebook_sizes"][0])
        n_vq = int(self.manifest["tts_config"]["n_vq"])
        repetition_seen_mask = np.zeros((1, n_vq, audio_codebook_size), dtype=np.int32)
        for channel_index, token_ids in enumerate(previous_token_sets_by_channel):
            for token_id in token_ids:
                if 0 <= token_id < audio_codebook_size:
                    repetition_seen_mask[0, channel_index, token_id] = 1
        outputs = self.sessions["local_greedy_frame"].run(
            None,
            {
                "global_hidden": global_hidden.astype(np.float32, copy=False),
                "repetition_seen_mask": repetition_seen_mask,
                "repetition_penalty": np.asarray([float(repetition_penalty)], dtype=np.float32),
            },
        )
        output_names = [output.name for output in self.sessions["local_greedy_frame"].get_outputs()]
        named_outputs = dict(zip(output_names, outputs, strict=True))
        should_continue = bool(int(np.asarray(named_outputs["should_continue"]).reshape(-1)[0]))
        frame_token_ids = np.asarray(named_outputs["frame_token_ids"]).reshape(-1).astype(np.int32, copy=False).tolist()
        return should_continue, [int(item) for item in frame_token_ids]

    def run_local_fixed_sampled_frame(
        self,
        global_hidden: np.ndarray,
        *,
        previous_token_sets_by_channel: list[set[int]],
    ) -> tuple[bool, list[int]]:
        audio_codebook_size = int(self.tts_meta["model_config"]["audio_codebook_sizes"][0])
        n_vq = int(self.manifest["tts_config"]["n_vq"])
        repetition_seen_mask = np.zeros((1, n_vq, audio_codebook_size), dtype=np.int32)
        for channel_index, token_ids in enumerate(previous_token_sets_by_channel):
            for token_id in token_ids:
                if 0 <= token_id < audio_codebook_size:
                    repetition_seen_mask[0, channel_index, token_id] = 1
        assistant_random_u = np.asarray([min(0.99999994, max(0.0, float(self.rng.random())))], dtype=np.float32)
        audio_random_u = np.asarray(
            [[min(0.99999994, max(0.0, float(self.rng.random()))) for _ in range(n_vq)]],
            dtype=np.float32,
        )
        outputs = self.sessions["local_fixed_sampled_frame"].run(
            None,
            {
                "global_hidden": global_hidden.astype(np.float32, copy=False),
                "repetition_seen_mask": repetition_seen_mask,
                "assistant_random_u": assistant_random_u,
                "audio_random_u": audio_random_u,
            },
        )
        output_names = [output.name for output in self.sessions["local_fixed_sampled_frame"].get_outputs()]
        named_outputs = dict(zip(output_names, outputs, strict=True))
        frame_token_ids = np.asarray(named_outputs["frame_token_ids"]).reshape(-1).astype(np.int32, copy=False).tolist()
        should_continue = bool(int(np.asarray(named_outputs["should_continue"]).reshape(-1)[0]))
        return should_continue, [int(item) for item in frame_token_ids]

    # ── codec audio decode ──

    def decode_full_audio(self, generated_frames: list[list[int]]) -> tuple[list[np.ndarray], int]:
        if not generated_frames:
            return [], 0
        audio_codes, dims = _flatten3d_int32([generated_frames])
        outputs = self.sessions["codec_decode"].run(
            None,
            {
                "audio_codes": audio_codes.reshape(dims),
                "audio_code_lengths": np.asarray([len(generated_frames)], dtype=np.int32),
            },
        )
        output_names = [output.name for output in self.sessions["codec_decode"].get_outputs()]
        named_outputs = dict(zip(output_names, outputs, strict=True))
        audio_length = int(named_outputs["audio_lengths"].reshape(-1)[0])
        return _slice_channel_major_audio(named_outputs["audio"], 0, audio_length), audio_length

    # ── main generation loop ──

    def generate_audio_frames(
        self,
        request_rows: dict[str, list[list[int]]],
        on_frame: Callable[[list[list[int]], int, list[int]], None] | None = None,
    ) -> list[list[int]]:
        generation_defaults = self.manifest["generation_defaults"]
        row_width = int(self.manifest["tts_config"]["n_vq"]) + 1
        prefill_ids, prefill_dims = _flatten3d_int32([request_rows["inputIds"]])
        prefill_mask, prefill_mask_dims = _flatten2d_int32(request_rows["attentionMask"])
        outputs = self.sessions["prefill"].run(
            None,
            {
                "input_ids": prefill_ids.reshape(prefill_dims),
                "attention_mask": prefill_mask.reshape(prefill_mask_dims),
            },
        )
        output_names = [output.name for output in self.sessions["prefill"].get_outputs()]
        named_outputs = dict(zip(output_names, outputs, strict=True))
        global_hidden = _extract_last_hidden(named_outputs["global_hidden"])
        past_valid_length = sum(int(item) for item in request_rows["attentionMask"][0])
        past_by_name: dict[str, np.ndarray] = {
            output_name.replace("present_", "past_"): named_outputs[output_name]
            for output_name in self.tts_meta["onnx"]["prefill_output_names"][1:]
        }
        generated_frames: list[list[int]] = []
        previous_tokens_by_channel: list[list[int]] = [[] for _ in range(int(self.manifest["tts_config"]["n_vq"]))]
        previous_token_sets_by_channel: list[set[int]] = [set() for _ in range(int(self.manifest["tts_config"]["n_vq"]))]

        for step_index in range(int(generation_defaults["max_new_frames"])):
            frame: list[int] = []

            if "local_greedy_frame" in self.sessions and not bool(generation_defaults["do_sample"]):
                should_continue, frame = self.run_local_greedy_frame(
                    global_hidden,
                    previous_token_sets_by_channel=previous_token_sets_by_channel,
                    repetition_penalty=float(generation_defaults["audio_repetition_penalty"]),
                )
                if not should_continue:
                    break
                for channel_index, sampled_token in enumerate(frame):
                    previous_tokens_by_channel[channel_index].append(sampled_token)
                    previous_token_sets_by_channel[channel_index].add(sampled_token)

            elif "local_fixed_sampled_frame" in self.sessions and generation_defaults["sample_mode"] == SAMPLE_MODE_FIXED:
                should_continue, frame = self.run_local_fixed_sampled_frame(
                    global_hidden,
                    previous_token_sets_by_channel=previous_token_sets_by_channel,
                )
                if not should_continue:
                    break
                for channel_index, sampled_token in enumerate(frame):
                    previous_tokens_by_channel[channel_index].append(sampled_token)
                    previous_token_sets_by_channel[channel_index].add(sampled_token)

            else:
                raise RuntimeError(
                    f"No applicable local frame session found. "
                    f"Available sessions: {list(self.sessions.keys())}, "
                    f"sample_mode={generation_defaults['sample_mode']}, "
                    f"do_sample={generation_defaults['do_sample']}"
                )

            generated_frames.append(frame)

            # Decode step: feed generated frame back
            next_row = np.full((1, 1, row_width), int(self.manifest["tts_config"]["audio_pad_token_id"]), dtype=np.int32)
            next_row[0, 0, 0] = int(self.manifest["tts_config"]["audio_assistant_slot_token_id"])
            for index, token in enumerate(frame):
                next_row[0, 0, index + 1] = int(token)
            decode_feeds: dict[str, np.ndarray] = {
                "input_ids": next_row,
                "past_valid_lengths": np.asarray([past_valid_length], dtype=np.int32),
            }
            for input_name in self.tts_meta["onnx"]["decode_input_names"][2:]:
                decode_feeds[input_name] = past_by_name[input_name]
            decode_outputs = self.sessions["decode"].run(None, decode_feeds)
            decode_output_names = [output.name for output in self.sessions["decode"].get_outputs()]
            named_decode_outputs = dict(zip(decode_output_names, decode_outputs, strict=True))
            global_hidden = _extract_last_hidden(named_decode_outputs["global_hidden"])
            past_valid_length += 1
            past_by_name = {
                output_name.replace("present_", "past_"): named_decode_outputs[output_name]
                for output_name in self.tts_meta["onnx"]["decode_output_names"][1:]
            }
            if on_frame is not None:
                on_frame(generated_frames, step_index, frame)

        return generated_frames


__all__ = [
    "EXECUTION_PROVIDER_CPU",
    "OrtCpuRuntime",
    "SAMPLE_MODE_FIXED",
    "SAMPLE_MODE_GREEDY",
    "_normalize_sample_mode",
]
