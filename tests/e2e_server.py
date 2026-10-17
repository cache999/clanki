"""clanki with a throwaway data dir, an in-memory AnkiConnect and (unless --real-llm) a fake LLM,
for end-to-end tests and for trying the UI without Anki.
Usage: uv run python tests/e2e_server.py [--port 18710] [--real-llm]"""
import argparse
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).parent))
import keyring  # noqa: E402

from fake_anki import FakeAnki  # noqa: E402
from fake_keyring import MemoryKeyring  # noqa: E402
from fake_llm import EchoLLM  # noqa: E402

from clanki.app import create_app  # noqa: E402
from clanki.config import Config  # noqa: E402


def serve_fake_anki(port: int) -> FakeAnki:
    fake = FakeAnki()

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                self._reply({"result": getattr(fake, "a_" + req["action"])(**req.get("params", {})), "error": None})
            except Exception as e:
                self._reply({"result": None, "error": str(e)})

        def do_GET(self):  # test hook: what Anki "contains"
            self._reply({str(k): v for k, v in fake.notes.items()})

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return fake


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18710)
    ap.add_argument("--anki-port", type=int, default=18765)
    ap.add_argument("--real-llm", action="store_true", help="use DeepSeek with DEEPSEEK_API_KEY (costs money)")
    args = ap.parse_args()
    serve_fake_anki(args.anki_port)
    provider_for = None  # clanki's default: DeepSeek with the configured key
    if not args.real_llm:
        os.environ.pop("DEEPSEEK_API_KEY", None)  # never spend money in tests
        keyring.set_keyring(MemoryKeyring())
        provider_for = EchoLLM
    data = Path(tempfile.mkdtemp(prefix="clanki-e2e-"))
    cfg = Config(data_dir=data, port=args.port, anki_url="http://127.0.0.1:%d" % args.anki_port)
    print("clanki e2e: http://127.0.0.1:%d/  data=%s" % (args.port, data), flush=True)
    uvicorn.run(create_app(cfg, provider_for=provider_for), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
