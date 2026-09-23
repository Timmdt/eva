from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Iterator


class XTTSEngine:
    """Owns one XTTS model and cached speaker conditioning inside the worker."""

    def __init__(
        self,
        *,
        model_name: str,
        references: list[Path],
        language: str,
        device: str,
        cache_dir: Path,
        cache_speaker: bool,
        low_vram_mode: bool,
        stream_chunk_size: int,
        streaming: bool = True,
        temperature: float = 0.75,
        repetition_penalty: float = 5.0,
        top_k: int = 50,
        top_p: float = 0.85,
        speed: float = 0.98,
        seed: int = 42,
        trim_trailing_artifacts: bool = False,
        gpt_cond_len: int = 12,
        gpt_cond_chunk_len: int = 4,
    ) -> None:
        self.model_name = model_name
        self.references = references
        self.language = language
        self.device_name = device
        self.cache_dir = cache_dir
        self.cache_speaker = cache_speaker
        self.low_vram_mode = low_vram_mode
        self.streaming = streaming
        self.stream_chunk_size = stream_chunk_size
        self.temperature = temperature
        self.repetition_penalty = repetition_penalty
        self.top_k = top_k
        self.top_p = top_p
        self.trim_trailing_artifacts = trim_trailing_artifacts
        self.speed = speed
        self.seed = seed
        self.gpt_cond_len = gpt_cond_len
        self.gpt_cond_chunk_len = min(gpt_cond_chunk_len, gpt_cond_len)
        self.api = None
        self.model = None
        self.torch = None
        self.gpt_cond_latent = None
        self.speaker_embedding = None
        self.sample_rate = 24_000
        self.load_ms = 0.0
        self.conditioning_ms = 0.0
        self.idle_vram_mb = 0
        self.peak_vram_mb = 0

    def _device(self, torch) -> str:
        requested = self.device_name
        if requested == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if requested.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("XTTS wurde für CUDA konfiguriert, aber CUDA ist nicht verfügbar.")
        return requested

    def _fingerprint(self) -> str:
        values = [
            self.model_name,
            self.language,
            str(self.gpt_cond_len),
            str(self.gpt_cond_chunk_len),
        ]
        for path in self.references:
            stat = path.stat()
            values.extend([str(path.resolve()), str(stat.st_size), str(stat.st_mtime_ns)])
        return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()[:24]

    def _cache_path(self) -> Path:
        return self.cache_dir / f"speaker-{self._fingerprint()}.pt"

    def _load_conditioning_cache(self, torch, device: str) -> bool:
        if not self.cache_speaker:
            return False
        path = self._cache_path()
        if not path.is_file():
            return False
        try:
            cached = torch.load(path, map_location="cpu", weights_only=True)
            self.gpt_cond_latent = cached["gpt_cond_latent"].to(device)
            self.speaker_embedding = cached["speaker_embedding"].to(device)
            return True
        except (OSError, KeyError, RuntimeError, TypeError):
            return False

    def _save_conditioning_cache(self, torch) -> None:
        if not self.cache_speaker:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self._cache_path()
        temporary = path.with_suffix(".tmp")
        torch.save(
            {
                "gpt_cond_latent": self.gpt_cond_latent.detach().cpu(),
                "speaker_embedding": self.speaker_embedding.detach().cpu(),
            },
            temporary,
        )
        os.chmod(temporary, 0o600)
        temporary.replace(path)

    def _memory(self) -> tuple[int, int]:
        if self.torch is None or not self.device_name.startswith("cuda"):
            return (0, 0)
        free, total = self.torch.cuda.mem_get_info()
        used_mb = round((total - free) / 1024 / 1024)
        total_mb = round(total / 1024 / 1024)
        self.peak_vram_mb = max(self.peak_vram_mb, used_mb)
        return used_mb, total_mb

    def load(self) -> dict[str, object]:
        import torch
        from TTS.api import TTS

        self.torch = torch
        device = self._device(torch)
        self.device_name = device
        started = time.perf_counter()
        self.api = TTS(model_name=self.model_name, progress_bar=False).to(device)
        self.model = self.api.synthesizer.tts_model
        self.model.eval()
        self.sample_rate = int(getattr(self.api.synthesizer, "output_sample_rate", 24_000))
        self.load_ms = (time.perf_counter() - started) * 1000.0
        used, total = self._memory()
        self.idle_vram_mb = used

        conditioning_started = time.perf_counter()
        cache_hit = self._load_conditioning_cache(torch, device)
        if not cache_hit:
            with torch.inference_mode():
                self.gpt_cond_latent, self.speaker_embedding = self.model.get_conditioning_latents(
                    audio_path=[str(path) for path in self.references],
                    max_ref_length=30,
                    gpt_cond_len=self.gpt_cond_len,
                    gpt_cond_chunk_len=self.gpt_cond_chunk_len,
                )
            self._save_conditioning_cache(torch)
        self.conditioning_ms = (time.perf_counter() - conditioning_started) * 1000.0
        used, total = self._memory()
        self.idle_vram_mb = used
        return {
            "device": device,
            "gpu": torch.cuda.get_device_name(0) if device.startswith("cuda") else None,
            "sample_rate": self.sample_rate,
            "load_ms": self.load_ms,
            "conditioning_ms": self.conditioning_ms,
            "conditioning_cache_hit": cache_hit,
            "idle_vram_mb": used,
            "total_vram_mb": total,
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
        }

    def warmup(self) -> float:
        started = time.perf_counter()
        cancel = threading.Event()
        for _chunk in self.stream_pcm("Hallo.", cancel):
            pass
        return (time.perf_counter() - started) * 1000.0

    def _trim_isolated_trailing_artifact(self, audio):
        """Remove a very short utterance after a clear final silence gap."""
        if not self.trim_trailing_artifacts or self.torch is None:
            return audio
        torch = self.torch
        samples = audio.detach().float().flatten()
        frame_size = max(1, self.sample_rate // 100)
        frame_count = samples.numel() // frame_size
        if frame_count < 50:
            return audio
        frames = samples[: frame_count * frame_size].reshape(frame_count, frame_size)
        rms = torch.sqrt(torch.mean(frames * frames, dim=1) + 1e-12)
        mask = (rms > 0.006).float().reshape(1, 1, -1)
        active = torch.nn.functional.max_pool1d(
            mask,
            kernel_size=7,
            stride=1,
            padding=3,
        ).bool().flatten().tolist()
        runs: list[tuple[int, int]] = []
        start = None
        for index, value in enumerate(active + [False]):
            if value and start is None:
                start = index
            elif not value and start is not None:
                runs.append((start, index))
                start = None
        if len(runs) < 2:
            return audio
        previous, trailing = runs[-2], runs[-1]
        gap_seconds = (trailing[0] - previous[1]) * frame_size / self.sample_rate
        trailing_seconds = (trailing[1] - trailing[0]) * frame_size / self.sample_rate
        suffix_seconds = (samples.numel() - trailing[0] * frame_size) / self.sample_rate
        if (
            gap_seconds < 0.20
            or trailing_seconds > 0.28
            or suffix_seconds > 0.55
        ):
            return audio
        clean_end = min(samples.numel(), previous[1] * frame_size)
        clean_tail = torch.zeros(
            round(0.12 * self.sample_rate), dtype=samples.dtype, device=samples.device
        )
        return torch.cat((samples[:clean_end], clean_tail))

    def _inference_chunks(self, text: str):
        self.torch.manual_seed(self.seed)
        if self.device_name.startswith("cuda"):
            self.torch.cuda.manual_seed_all(self.seed)
        parameters = {
            "temperature": self.temperature,
            "repetition_penalty": self.repetition_penalty,
            "top_k": self.top_k,
            "top_p": self.top_p,
            "speed": self.speed,
            "enable_text_splitting": False,
        }
        if self.streaming:
            return self.model.inference_stream(
                text,
                self.language,
                self.gpt_cond_latent,
                self.speaker_embedding,
                stream_chunk_size=self.stream_chunk_size,
                **parameters,
            )
        output = self.model.inference(
            text,
            self.language,
            self.gpt_cond_latent,
            self.speaker_embedding,
            **parameters,
        )
        audio = self.torch.as_tensor(output["wav"])
        return (self._trim_isolated_trailing_artifact(audio),)

    def stream_pcm(self, text: str, cancel: threading.Event) -> Iterator[bytes]:
        if self.model is None or self.torch is None:
            raise RuntimeError("XTTS ist noch nicht geladen.")
        torch = self.torch
        started = time.perf_counter()
        samples = 0
        with torch.inference_mode():
            chunks = self._inference_chunks(text)
            for chunk in chunks:
                if cancel.is_set():
                    break
                audio = chunk.detach().float().clamp(-1.0, 1.0).cpu().numpy()
                pcm = (audio * 32767.0).astype("<i2", copy=False).tobytes()
                samples += len(pcm) // 2
                self._memory()
                yield pcm
                del audio, pcm, chunk
        duration = samples / self.sample_rate if self.sample_rate else 0.0
        elapsed = time.perf_counter() - started
        self._memory()
        self.last_metrics = {
            "audio_seconds": duration,
            "synthesis_seconds": elapsed,
            "real_time_factor": elapsed / duration if duration else 0.0,
            "peak_vram_mb": self.peak_vram_mb,
            "idle_vram_mb": self.idle_vram_mb,
        }

    def status(self) -> dict[str, object]:
        used, total = self._memory()
        return {
            "loaded": self.model is not None,
            "seed": self.seed,
            "model": self.model_name,
            "device": self.device_name,
            "sample_rate": self.sample_rate,
            "used_vram_mb": used,
            "total_vram_mb": total,
            "peak_vram_mb": self.peak_vram_mb,
            "idle_vram_mb": self.idle_vram_mb,
            "load_ms": self.load_ms,
            "conditioning_ms": self.conditioning_ms,
        }
