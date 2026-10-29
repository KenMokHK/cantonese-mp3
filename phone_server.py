"""Phone page for Cantonese MP3. Open this computer's address on the same Wi-Fi."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import edge_tts

from text_clean import prepare_spoken_text

PORT = 8765
PAGE = Path(__file__).with_name("phone.html").read_text(encoding="utf-8")
VOICES = {
    "zh-HK-HiuMaanNeural": "你好，我係曉曼。呢個係女聲示範。",
    "zh-HK-HiuGaaiNeural": "你好，我係曉佳。呢個係女聲示範。",
    "zh-HK-WanLungNeural": "你好，我係雲龍。呢個係男聲示範。",
}
DEMO_DIR = Path.home() / "AppData" / "Local" / "CantoneseMP3" / "voice-demos"
DEMO_DIR.mkdir(parents=True, exist_ok=True)
_LOCK = threading.Lock()


def lan_ip() -> str:
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        address = probe.getsockname()[0]
        probe.close()
        return address
    except OSError:
        return "127.0.0.1"


def checked_rate(raw: str) -> str:
    try:
        number = int(str(raw).replace("%", "").replace("+", ""))
    except ValueError:
        number = -6
    number = max(-30, min(30, number))
    return f"{number:+d}%"


def checked_voice(raw: str) -> str:
    if raw in VOICES:
        return raw
    return "zh-HK-HiuMaanNeural"


async def audio_bytes(text: str, voice: str, rate: str) -> bytes:
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    chunks: list[bytes] = []
    async for message in communicate.stream():
        if message["type"] == "audio":
            chunks.append(message["data"])
    if not chunks:
        raise RuntimeError("no audio")
    return b"".join(chunks)


def demo_file(voice: str, rate: str) -> Path:
    safe_rate = rate.replace("%", "").replace("+", "p").replace("-", "m")
    path = DEMO_DIR / f"{voice}_{safe_rate}.mp3"
    if path.exists() and path.stat().st_size > 1000:
        return path
    data = asyncio.run(audio_bytes(VOICES[voice], voice, rate))
    path.write_bytes(data)
    return path


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("expected an object")
        return data

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/phone.html"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/info":
            self._json(200, {"ip": lan_ip(), "port": PORT, "voices": list(VOICES)})
            return
        if parsed.path == "/api/demo":
            query = parse_qs(parsed.query)
            voice = checked_voice(query.get("voice", [""])[0])
            rate = checked_rate(query.get("rate", ["-6%"])[0])
            try:
                with _LOCK:
                    path = demo_file(voice, rate)
                self._send(200, path.read_bytes(), "audio/mpeg")
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            data = self._read_json()
        except Exception:
            self._json(400, {"error": "無法讀取文字。"})
            return
        if parsed.path == "/api/clean":
            spoken, removed = prepare_spoken_text(str(data.get("text", "")))
            self._json(200, {"text": spoken, "removed": removed})
            return
        if parsed.path == "/api/mp3":
            spoken, removed = prepare_spoken_text(str(data.get("text", "")))
            if not spoken:
                self._json(400, {"error": "請輸入可以朗讀嘅文字。表情符號已經移除。"})
                return
            if len(spoken) > 15000:
                self._json(400, {"error": "文字太長，請分段，每次少過一萬五千字。"})
                return
            voice = checked_voice(str(data.get("voice", "")))
            rate = checked_rate(str(data.get("rate", "-6%")))
            try:
                payload = asyncio.run(audio_bytes(spoken, voice, rate))
            except Exception as exc:
                self._json(500, {"error": f"無法產生 MP3。請檢查網絡。{exc}"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Removed-Emoji", str(removed))
            self.send_header("X-Spoken-Text", "see-body")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        self._json(404, {"error": "not found"})


def main() -> None:
    address = lan_ip()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"This computer: http://127.0.0.1:{PORT}", flush=True)
    print(f"Phone, same Wi-Fi: http://{address}:{PORT}", flush=True)
    print("Leave this window open. Close it when you are finished.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
