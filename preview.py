"""Local Viking invitation color editor. Run with uv run python preview.py."""
import argparse
import json
import re
import secrets
import tempfile
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from generate import ROOT, data_uri

THEME = ROOT / "templates/invitation_viking.css"
COLOR_LABELS = {
    "text-color": "General text",
    "accent-color": "Highlighted text",
    "gift-color": "Gift suggestions",
    "outline-color": "Text outline",
    "ornament-color": "Flourishes and stars",
    "ornament-outline": "Ornament outline",
    "page-color": "Page margins",
    "paper-color": "Background fallback",
}


def read_colors(path=THEME):
    css = path.read_text(encoding="utf-8")
    result = {}
    for key in COLOR_LABELS:
        match = re.search(r"--" + re.escape(key) + r"\s*:\s*(#[0-9a-fA-F]{6})\s*;", css)
        if not match:
            raise ValueError(f"Missing six-digit hex color --{key} in {path.name}")
        result[key] = match[1].lower()
    return result


def save_colors(colors, path=THEME):
    """Update only known color variables, preserving comments and custom CSS."""
    if not isinstance(colors, dict) or set(colors) != set(COLOR_LABELS):
        raise ValueError("Provide exactly the known theme color fields.")
    if any(not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value)
           for value in colors.values()):
        raise ValueError("Colors must use six-digit hex notation, such as #fff2ce.")
    read_colors(path)  # Reject an invalid file instead of silently missing edits.
    css = path.read_text(encoding="utf-8")
    for key, value in colors.items():
        css = re.sub(r"(--" + re.escape(key) + r"\s*:\s*)#[0-9a-fA-F]{6}(\s*;)",
                     lambda match: match[1] + value.lower() + match[2], css)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(css)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def make_handler(background, name, token):
    environment = Environment(loader=FileSystemLoader(ROOT / "templates"),
                              autoescape=select_autoescape(["html"]), undefined=StrictUndefined)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, body, content_type="text/html; charset=utf-8", status=200):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            try:
                if url.path == "/":
                    self.respond(environment.get_template("preview_editor.html").render(
                        token=token, name=name, labels=COLOR_LABELS, colors=read_colors()))
                elif url.path == "/invitation":
                    guest = parse_qs(url.query).get("name", [name])[0][:300]
                    self.respond(environment.get_template("invitation_viking.html").render(
                        name=guest, font=data_uri(ROOT / "assets/fonts/BerkshireSwash-Regular.ttf", "font/ttf"),
                        background=data_uri(background), width=1085, height=2048))
                else:
                    self.respond("Not found", "text/plain", 404)
            except (OSError, ValueError) as error:
                self.respond(str(error), "text/plain; charset=utf-8", 400)

        def do_POST(self):
            # A per-session header prevents other web pages from writing local CSS.
            if self.path != "/colors" or self.headers.get("X-Preview-Token") != token:
                self.respond("Forbidden", "text/plain", 403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("Invalid request size.")
                colors = json.loads(self.rfile.read(length))
                save_colors(colors)
                self.respond(json.dumps({"saved": True}), "application/json")
            except (OSError, ValueError, UnicodeError) as error:
                self.respond(str(error), "text/plain; charset=utf-8", 400)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--background", type=Path, default=ROOT / "backgrounds/B.png")
    parser.add_argument("--name", default="Tiya Lety", help="Sample guest name; no guest list is needed.")
    parser.add_argument("--port", type=int, default=8765, help="Local port (0 chooses an available port).")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically.")
    args = parser.parse_args()
    if not args.background.is_file():
        parser.error(f"Background not found: {args.background}. Pass --background PATH.")
    if not 0 <= args.port <= 65535:
        parser.error("Port must be between 0 and 65535.")
    try:
        read_colors()
        server = HTTPServer(("127.0.0.1", args.port),
                            make_handler(args.background.resolve(), args.name, secrets.token_urlsafe(32)))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Unable to start preview: {error}\nTry --port 0 if the port is occupied.\n")
    address = f"http://127.0.0.1:{server.server_port}/"
    print(f"Preview: {address}\nSave colors writes {THEME}\nPress Ctrl+C to stop.", flush=True)
    if not args.no_open:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
