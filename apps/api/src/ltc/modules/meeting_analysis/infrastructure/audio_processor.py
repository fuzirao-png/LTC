"""Audio processing via FFmpeg (imageio-ffmpeg).

Provides extract-audio, normalize, split, and probe-duration utilities
for meeting media files.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


class AudioProcessingError(RuntimeError):
    """Raised when ffmpeg fails during audio processing."""


class MediaExtractionError(RuntimeError):
    """Raised when ffmpeg fails during media extraction."""


def _ffmpeg() -> str:
    """Return the path to the ffmpeg binary."""
    try:
        from imageio_ffmpeg import get_ffmpeg_exe  # type: ignore[import-untyped]

        return get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def extract_audio_from_video(video_path: str, target_dir: str) -> str:
    """Extract audio track from a video file as MP3.

    Returns the path to the extracted audio file.
    """
    dest_dir = Path(target_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    src_stem = Path(video_path).stem
    output_path = dest_dir / f"{src_stem}_extracted.mp3"

    cmd = [
        _ffmpeg(),
        "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "libmp3lame",
        "-q:a", "2",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise MediaExtractionError(f"Failed to extract audio: {exc.stderr}") from exc
    return str(output_path)


def normalize_audio(source_path: str, target_dir: str) -> str:
    """Convert audio to 16 kHz mono WAV.

    Returns the path to the normalized WAV file.
    """
    dest_dir = Path(target_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    src_stem = Path(source_path).stem
    output_path = dest_dir / f"{src_stem}_norm.wav"

    cmd = [
        _ffmpeg(),
        "-y",
        "-i", str(source_path),
        "-ac", "1",
        "-ar", "16000",
        "-sample_fmt", "s16",
        "-vn",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise AudioProcessingError(f"Failed to normalize audio: {exc.stderr}") from exc
    return str(output_path)


def probe_duration(source_path: str) -> float:
    """Return the duration (seconds) of the media file at *source_path*."""
    cmd = [_ffmpeg(), "-i", str(source_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise AudioProcessingError(f"Failed to probe duration: {exc.stderr}") from exc

    # ffmpeg writes info to stderr; look for "Duration: HH:MM:SS.mm"
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
    if not match:
        raise AudioProcessingError("Could not parse duration from ffmpeg output")
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return hours * 3600.0 + minutes * 60.0 + seconds


def split_audio(source_path: str, target_dir: str, chunk_seconds: int = 60) -> list[str]:
    """Split a WAV file into chunks of *chunk_seconds* each.

    Returns a list of file paths for each chunk.
    """
    total_duration = probe_duration(source_path)
    dest_dir = Path(target_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    src_stem = Path(source_path).stem

    chunk_count = max(1, int(total_duration / chunk_seconds) + (1 if total_duration % chunk_seconds > 0 else 0))
    chunk_paths: list[str] = []

    for i in range(chunk_count):
        start = i * chunk_seconds
        chunk_duration = min(chunk_seconds, total_duration - start)
        if chunk_duration <= 0:
            break
        output_path = dest_dir / f"{src_stem}_chunk_{i:03d}.wav"
        cmd = [
            _ffmpeg(),
            "-y",
            "-i", str(source_path),
            "-ss", str(start),
            "-t", str(chunk_duration),
            "-ac", "1",
            "-ar", "16000",
            "-sample_fmt", "s16",
            str(output_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise AudioProcessingError(f"Failed to split audio chunk {i}: {exc.stderr}") from exc
        if output_path.stat().st_size <= 44:  # WAV header is 44 bytes
            raise AudioProcessingError(f"Empty audio chunk {i}")
        chunk_paths.append(str(output_path))

    return chunk_paths
