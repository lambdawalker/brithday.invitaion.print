"""Render one HTML preview and JPEG invitation per guest."""
import argparse
import base64
import csv
from collections import Counter
from html import unescape
import json
import math
import mimetypes
import re
import unicodedata
from io import BytesIO
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from PIL import Image
from playwright.sync_api import Error as PlaywrightError, sync_playwright

ROOT = Path(__file__).resolve().parent


def data_uri(path: Path, mime: str | None = None) -> str:
    content_type = mime or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{content_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def filename(index: int, name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:60] or "guest"
    return f"{index:03d}-{slug}"



def read_guests(path: Path) -> list[tuple[str, str]]:
    """Read Name, F|M|P rows without guessing the form of address."""
    guests = []
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        for row in reader:
            if not row or not any(cell.strip() for cell in row):
                continue
            if len(row) != 2 or not row[0].strip() or row[1].strip().upper() not in {"F", "M", "P"}:
                raise ValueError(f"Invalid guest row at line {reader.line_num}: expected Name LastName, F|M|P.")
            guests.append((row[0].strip(), row[1].strip().upper()))
    if not guests:
        raise ValueError("The names file must contain at least one guest.")
    return guests


def read_completed(output: Path) -> list[dict[str, str]]:
    """Load the manifest, or migrate pre-manifest batches from their previews."""
    manifest = output / "manifest.json"
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("invitations"), list):
            raise ValueError(f"Unsupported or malformed manifest: {manifest}")
        entries = data["invitations"]
    else:
        entries = legacy_entries(output)
    valid = []
    seen = set()
    for entry in entries:
        if (not isinstance(entry, dict) or not all(isinstance(entry.get(key), str) for key in ("name", "gender", "image", "html"))
                or entry["gender"] not in {"F", "M", "P"}
                or any(not entry[key] or "/" in entry[key] or "\\" in entry[key] or ":" in entry[key] or entry[key] in {".", ".."} for key in ("image", "html"))):
            raise ValueError(f"Invalid invitation entry in {manifest}")
        if entry["image"] in seen:
            continue
        try:
            with Image.open(output / entry["image"]) as image:
                image.verify()
        except (OSError, ValueError):
            continue
        valid.append(entry)
        seen.add(entry["image"])
    return valid


def save_manifest(output: Path, entries: list[dict[str, str]]) -> None:
    temporary = output / "manifest.json.tmp"
    temporary.write_text(json.dumps({"version": 1, "invitations": entries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output / "manifest.json")


def legacy_entries(output: Path) -> list[dict[str, str]]:
    entries = []
    for path in output.iterdir():
        if path.suffix != ".html":
            continue
        # A preview alone is not a completed export. Retry missing/broken images.
        image_path = next((path.with_suffix(ext) for ext in (".jpg", ".png")
                           if path.with_suffix(ext).is_file()), None)
        if image_path is None:
            continue
        try:
            with Image.open(image_path) as image:
                image.verify()
            html = path.read_text(encoding="utf-8")
        except (OSError, ValueError):
            continue
        name = re.search(r'<text\b[^>]*\bid="guest"[^>]*>(.*?)</text>', html, re.DOTALL)
        form = re.search(r">Est(?:ás|án) (invitada|invitado|invitados) al</text>", html)
        if name and form:
            gender = {"invitada": "F", "invitado": "M", "invitados": "P"}[form[1]]
            entries.append({"name": unescape(name[1]), "gender": gender, "image": image_path.name, "html": path.name})
    return entries


def pending_guests(output: Path, guests: list[tuple[str, str]], entries: list[dict[str, str]]) -> list[tuple[str, str, str]]:
    completed = Counter((entry["name"], entry["gender"]) for entry in entries)
    next_index = 1
    for path in output.iterdir():
        match = re.match(r"^(\d+)-", path.name)
        if match:
            next_index = max(next_index, int(match[1]) + 1)
    pending = []
    for name, gender in guests:
        if completed[(name, gender)]:
            completed[(name, gender)] -= 1
            print(f"Skipping already rendered: {name}, {gender}")
        else:
            pending.append((filename(next_index, name), name, gender))
            next_index += 1
    return pending


def read_lists(directory: Path) -> list[tuple[str, list[tuple[str, str]]]]:
    """Read each top-level text file before starting a release."""
    if not directory.is_dir():
        raise ValueError(f"Guest list folder not found: {directory}. Create it and add .txt guest lists, or pass --lists PATH.")
    paths = sorted((p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".txt"), key=lambda p: p.name.casefold())
    if not paths:
        raise ValueError(f"No .txt guest lists found in {directory}.")
    batches = []
    seen = set()
    for path in paths:
        if path.stem.casefold() in seen:
            raise ValueError(f"Guest list filenames must have distinct names (ignoring case): {path.name}")
        seen.add(path.stem.casefold())
        try:
            batches.append((path.stem, read_guests(path)))
        except (ValueError, csv.Error) as error:
            raise ValueError(f"{path}: {error}") from error
    return batches


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--lists", type=Path, default=Path("lists"), help="Folder of .txt guest lists (default: ./lists).")
    inputs.add_argument("--names", type=Path, help="Render one guest list using the original flat output layout.")
    parser.add_argument("--background", type=Path, help="Local PNG, JPG, or WebP background.")
    parser.add_argument("--resume", action="store_true", help="Add missing guests to the latest output folder, preserving existing invitations.")
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    design = parser.add_mutually_exclusive_group()
    design.add_argument("--layout", choices=("classic", "viking"), default="classic", help="Built-in layout (default: classic). Viking emphasizes the new 4 p.m. time.")
    design.add_argument("--template", type=Path, help="Custom HTML template instead of a built-in layout.")
    parser.add_argument("--width", type=int, help="Canvas width (classic: 896; viking: 1136).")
    parser.add_argument("--height", type=int, help="Canvas height (classic: 1184; viking: 1536).")
    parser.add_argument("--scale", type=float, default=2, help="Render pixel density before resizing (default: 2). Does not change layout.")
    parser.add_argument("--size-percent", type=float, default=75, help="Export width and height as a percentage of rendered pixels (1–100; default: 75).")
    parser.add_argument("--quality", type=int, default=90, help="JPEG quality (1–95; default: 90). Higher values make larger files.")
    args = parser.parse_args()
    design_size = (1136, 1536) if args.layout == "viking" else (896, 1184)
    args.width = args.width if args.width is not None else design_size[0]
    args.height = args.height if args.height is not None else design_size[1]
    args.template = args.template or ROOT / "templates" / ("invitation_viking.html" if args.layout == "viking" else "invitation.html")
    # Keep resume scoped to this design; classic releases retain their old paths.
    if args.layout == "viking":
        args.output = args.output / "viking"
    if args.width <= 0 or args.height <= 0:
        parser.error("Width and height must be positive.")
    if not math.isfinite(args.scale) or not 1 <= args.scale <= 4:
        parser.error("Scale must be between 1 and 4.")
    if not math.isfinite(args.size_percent) or not 1 <= args.size_percent <= 100:
        parser.error("Size percent must be between 1 and 100.")
    if not 1 <= args.quality <= 95:
        parser.error("Quality must be between 1 and 95.")
    try:
        batches = [(None, read_guests(args.names))] if args.names else read_lists(args.lists)
        args.output.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        previous = sorted(path for path in args.output.iterdir()
                          if path.is_dir() and re.fullmatch(r"\d{8}-\d{6}-\d{6}", path.name))
        release = previous[-1] if args.resume and previous else args.output / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        release.mkdir(exist_ok=True)
        jobs = []
        for list_name, guests in batches:
            output = release / list_name if list_name is not None else release
            output.mkdir(exist_ok=True)
            entries = read_completed(output)
            save_manifest(output, entries)
            print(f"Output folder: {output}")
            jobs.extend((output, entries, stem, name, gender)
                        for stem, name, gender in pending_guests(output, guests, entries))
        if not jobs:
            print("All guests are already rendered.")
            return
        background = data_uri(args.background) if args.background else None
        font = data_uri(ROOT / "assets/fonts/BerkshireSwash-Regular.ttf", "font/ttf")
        environment = Environment(
            loader=FileSystemLoader(args.template.resolve().parent),
            autoescape=select_autoescape(["html"]),
            undefined=StrictUndefined,
        )
        template = environment.get_template(args.template.name)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": args.width, "height": args.height}, device_scale_factor=args.scale)
            for output, entries, stem, name, gender in jobs:
                html = template.render(name=name, invitation_word={"F": "invitada", "M": "invitado", "P": "invitados"}[gender], invitation_verb="Están" if gender == "P" else "Estás", background=background, font=font, width=args.width, height=args.height)
                html_path = output / f"{stem}.html"
                html_path.write_text(html, encoding="utf-8")
                page.goto(html_path.resolve().as_uri(), wait_until="load")
                page.evaluate("async () => { await document.fonts.ready; await Promise.all(Array.from(document.images, image => image.decode())); }")
                page.evaluate("async () => { if (window.invitationReady) await window.invitationReady; }")
                if not page.evaluate('document.fonts.check(\'32px "Berkshire Swash"\')'):
                    raise ValueError("Berkshire Swash did not load.")
                # Resize a lossless render, then encode JPEG only once. Full chroma
                # resolution protects the raspberry lettering and ornament edges.
                with Image.open(BytesIO(page.screenshot(type="png"))) as rendered:
                    image = rendered.convert("RGB")
                size = tuple(max(1, round(dimension * args.size_percent / 100)) for dimension in image.size)
                if size != image.size:
                    image = image.resize(size, Image.Resampling.LANCZOS)
                image_path = output / f"{stem}.jpg"
                image.save(image_path, "JPEG", quality=args.quality, subsampling=0, optimize=True, progressive=True)
                entries.append({"name": name, "gender": gender, "image": image_path.name, "html": html_path.name})
                save_manifest(output, entries)
                print(f"Created {image_path} ({size[0]} × {size[1]}, {image_path.stat().st_size / 1024:.0f} KiB)")
            browser.close()
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(1, f"Unable to generate invitations: {error}\n")
    except PlaywrightError as error:
        parser.exit(1, f"Unable to render invitations: {error}\nIf Chromium is missing, run: uv run python -m playwright install chromium\n")


if __name__ == "__main__":
    main()
