import itertools
import os
import re
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash-preview-04-17")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("GEMINI_API_KEY", os.getenv("OPENAI_API_KEY", "")))


# ---------------------------------------------------------------------------
# Text Chunking Helpers
# ---------------------------------------------------------------------------

TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")

def split_into_chunks(raw_text: str) -> list[dict]:
    """
    Split the raw transcript into chunks, one per timestamp block.
    Each chunk is a dict with 'timestamp' and 'text'.
    Lines before the first timestamp are grouped under timestamp '00:00:00'.
    """
    chunks = []
    current_timestamp = "00:00:00"
    current_lines = []

    for line in raw_text.splitlines():
        stripped = line.strip()
        if TIMESTAMP_RE.match(stripped):
            if current_lines:
                chunks.append({
                    "timestamp": current_timestamp,
                    "text": "\n".join(current_lines).strip(),
                })
            current_timestamp = stripped
            current_lines = []
        else:
            current_lines.append(line)

    # Last chunk
    if current_lines:
        chunks.append({
            "timestamp": current_timestamp,
            "text": "\n".join(current_lines).strip(),
        })

    return [c for c in chunks if c["text"]]


def merge_chunks(chunks: list[dict], chunks_per_call: int) -> list[dict]:
    """
    Group consecutive timestamp chunks into batches of `chunks_per_call`.
    Each batch is merged into a single dict with the first timestamp and combined text.
    """
    if chunks_per_call <= 1:
        return chunks

    merged = []
    for i in range(0, len(chunks), chunks_per_call):
        batch = chunks[i:i + chunks_per_call]
        combined_text = "\n\n".join(
            f"{c['timestamp']}\n{c['text']}" for c in batch
        )
        merged.append({
            "timestamp": batch[0]["timestamp"],
            "text": combined_text,
        })
    return merged


# ---------------------------------------------------------------------------
# Terminal UX Helpers
# ---------------------------------------------------------------------------

class Spinner:
    """Simple terminal spinner for blocking operations."""

    def __init__(self, message: str):
        self.message = message
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self) -> None:
        for frame in itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
            if self._stop_event.is_set():
                break
            elapsed = time.time() - self.start_time
            print(f"\r  {frame} {self.message} ({elapsed:.1f}s)", end="", flush=True)
            time.sleep(0.1)

    def __enter__(self):
        self.start_time = time.time()
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop_event.set()
        self._thread.join()
        print("\r" + " " * (len(self.message) + 20) + "\r", end="", flush=True)
