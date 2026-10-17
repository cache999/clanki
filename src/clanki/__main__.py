"""`uv run clanki`: start the server and open the UI in the browser."""
import argparse
import threading
import webbrowser
from pathlib import Path

import uvicorn

from .app import create_app
from .config import load_config


def main(argv=None):
    ap = argparse.ArgumentParser(prog="clanki", description=__doc__)
    ap.add_argument("--port", type=int, help="default 8710, or `port` in config.toml")
    ap.add_argument("--data-dir", type=Path, help="where documents and cards are stored")
    ap.add_argument("--no-browser", action="store_true", help="don't open the browser")
    args = ap.parse_args(argv)
    cfg = load_config()
    if args.port:
        cfg.port = args.port
    if args.data_dir:
        cfg.data_dir = args.data_dir
    url = "http://%s:%d/" % (cfg.host, cfg.port)
    print("clanki: %s  (data: %s)" % (url, cfg.data_dir))
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, (url,)).start()
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, log_level="warning")


if __name__ == "__main__":
    main()
