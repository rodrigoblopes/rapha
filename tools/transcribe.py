"""Transcribe the Projeto 60 Dias video modules with faster-whisper.

⚠️ **Extraction tooling, not a runtime dependency (ADR-004).** This lives under
`tools/` and is never imported by `src/rapha/`. `ffmpeg` and `faster-whisper` exist
only to run it, once, and are in the optional `extract` dependency group.

Why local Whisper rather than a hosted transcriber (ADR-004): the modules are
purchased material and privacy-sensitive, so nothing is shipped to a third party.
On the RTX 3070 the medium model runs comfortably; on CPU it still works, slower.

The output — the transcripts — are written to `%RAPHA_HOME%/protocol/transcripts/`,
never the repo, for the same reason the extracted fichas are (ADR-002).

Usage:

    python tools/transcribe.py --module 17          # just the progression rule
    python tools/transcribe.py --module 16 17 18    # the rules modules
    python tools/transcribe.py --all                # everything (6.2 GB)

The linchpin is Módulo 17 (Como Progredir Cargas): its load-progression rule is
the method, and it exists only as video. Do that one first.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# The Windows console is cp1252; module names and log arrows are not. Force UTF-8
# so a print of a Portuguese module title does not crash the whole run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _add_cuda_dlls_to_path() -> None:
    """Put the pip-installed CUDA runtime DLLs on the search path.

    CTranslate2 (faster-whisper's backend) needs cublas64_12.dll and cudnn on the
    DLL path for GPU inference. The nvidia-*-cu12 wheels ship them under
    site-packages/nvidia/*/bin but do not register them, so a bare GPU run fails
    with "cublas64_12.dll not found". Adding them here keeps the whole CUDA
    dependency inside the venv rather than on the system.
    """
    import sysconfig

    site = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
    if not site.is_dir():
        return
    for bin_dir in site.glob("*/bin"):
        os.add_dll_directory(str(bin_dir))
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


_add_cuda_dlls_to_path()

HOME = Path(os.environ.get("RAPHA_HOME", Path.home() / ".rapha"))
FFMPEG = HOME / "tools" / "ffmpeg.exe"
OUT = HOME / "protocol" / "transcripts"
COURSE = Path(os.environ.get("COURSE_DIR", r"E:\Cursos\Projeto 60 Dias"))

# Portuguese fitness content. The medium model handles the domain vocabulary
# (exercise names, "progressão de carga") noticeably better than small.
MODEL = os.environ.get("WHISPER_MODEL", "medium")


def module_dirs(numbers: list[str]) -> list[Path]:
    want = tuple(numbers)
    return [
        d
        for d in sorted(COURSE.iterdir())
        if d.is_dir()
        and any(f" {n} " in d.name or f" {n} -" in d.name or f"{n} -" in d.name for n in want)
    ]


def extract_audio(video: Path, wav: Path) -> None:
    """Down-mix to 16 kHz mono WAV — what Whisper wants, and small."""
    subprocess.run(
        [
            str(FFMPEG), "-nostdin", "-y", "-i", str(video),
            "-ac", "1", "-ar", "16000", "-vn", str(wav),
        ],
        check=True,
        capture_output=True,
    )


def transcribe_module(model, module: Path) -> dict:
    videos = sorted(module.glob("*.mp4"))
    module_out = OUT / module.name
    module_out.mkdir(parents=True, exist_ok=True)

    done = []
    for video in videos:
        target = module_out / f"{video.stem}.txt"
        if target.exists() and target.stat().st_size > 0:
            print(f"    - {video.name} (already done)", flush=True)
            done.append(target.name)
            continue

        print(f"    >> {video.name}", flush=True)
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "audio.wav"
            extract_audio(video, wav)
            segments, _ = model.transcribe(str(wav), language="pt", vad_filter=True)

            lines: list[str] = []
            for seg in segments:
                stamp = time.strftime("%H:%M:%S", time.gmtime(seg.start))
                lines.append(f"[{stamp}] {seg.text.strip()}")

        target.write_text("\n".join(lines), encoding="utf-8")
        done.append(target.name)
        print(f"      {len(lines)} segments -> {target.name}", flush=True)

    return {"module": module.name, "videos": len(videos), "transcribed": done}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", nargs="+", help="module numbers, e.g. 17 or 16 17 18")
    parser.add_argument("--all", action="store_true", help="every video module")
    parser.add_argument("--device", default="auto", help="auto | cuda | cpu")
    args = parser.parse_args(argv)

    if not FFMPEG.exists():
        print(f"ffmpeg not found at {FFMPEG}", file=sys.stderr)
        return 2

    if args.all:
        numbers = [f"{n:02d}" for n in range(1, 26)]
    elif args.module:
        numbers = [n.zfill(2) for n in args.module]
    else:
        parser.error("give --module <n...> or --all")

    modules = module_dirs(numbers)
    if not modules:
        print(f"no matching module directories under {COURSE}", file=sys.stderr)
        return 1

    from faster_whisper import WhisperModel

    device = args.device
    compute = "float16" if device == "cuda" else "int8"
    if device == "auto":
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() > 0:
                device, compute = "cuda", "float16"
            else:
                device, compute = "cpu", "int8"
        except Exception:
            device, compute = "cpu", "int8"

    print(f"loading {MODEL} on {device} ({compute})", flush=True)
    model = WhisperModel(MODEL, device=device, compute_type=compute)

    OUT.mkdir(parents=True, exist_ok=True)
    summary = []
    for module in modules:
        print(f"\n## {module.name}", flush=True)
        summary.append(transcribe_module(model, module))

    (OUT / "index.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\ntranscripts in {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
