# Abi's second birthday invitations

Minimal Python starter: Jinja2 fills an HTML/CSS template and Playwright's Chromium renders one JPEG per guest. The layout follows the approved cloud-and-castle preview, with an arched headline, Berkshire Swash lettering, and canvas flourishes.

## Setup

Install Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from this repository:

```sh
uv sync
uv run playwright install chromium
uv run python generate.py --names examples/names.txt
```

On Linux, if browser system libraries are missing, use `uv run playwright install --with-deps chromium`.

## Personalize

Put your guest lists in `./lists` (relative to your working directory), for example `lists/mama.txt` and `lists/papa.txt`. Each UTF-8 `.txt` file uses the same format, with one guest and F/M/P code per line:

```text
Tiyo Baltazar, M
Tiya María, F
Tiyo Juan, M
Tiyos María y Juan, P
```

Run all the lists:

```sh
uv run python generate.py --background img.png
```

A release creates `output/<timestamp>/mama/` and `output/<timestamp>/papa/`, each with its own numbered JPEGs, HTML previews, and `manifest.json`. The same guest can appear independently in both lists. All top-level `.txt` files are read in filename order; other file types and nested folders are ignored. List files must be nonempty and valid; errors identify the source file before rendering begins. Personal files under `lists/` are ignored by Git.

Use `--lists another-folder` to change the input folder. The previous single-list command remains supported with a flat release layout:

```sh
uv run python generate.py --names guests.txt --background img.png
```

Without a background, the template uses a pastel gradient. PNG, JPEG, and WebP backgrounds are supported. Use the supplied 896 × 1184 composition (or an image with the same aspect ratio). The background is contained without cropping. Other background proportions may leave margins and will require layout adjustments.

Each run creates a new timestamped folder under `output/`, containing a standalone HTML preview and a 1344 × 1776 JPEG for each guest. Numbered filenames keep repeated names distinct. HTML escapes guest names; accents are preserved in the invitation.

Options: `--lists`, `--names`, `--resume`, `--background`, `--output`, `--template`, `--width`, `--height`, `--scale`, `--size-percent`, `--quality`. Paths you supply are relative to your working directory. The 896 × 1184 design scales uniformly into the requested canvas; differing aspect ratios leave margins. Ornament canvases render at least 4× internally, with smooth raspberry curves (#a82d60), matching the guest name, and cream outlines.

## Smaller JPEG exports

```sh
uv run python generate.py --names guests.txt --background img.png --size-percent 75 --quality 90
```

These are the defaults. The renderer first draws at `--scale 2` (1792 × 2368 pixels), then resizes each dimension to 75% (1344 × 1776) using Lanczos and saves a progressive, optimized JPEG. `--size-percent` accepts 1–100, including fractional values; it changes pixel dimensions, not a target file size. Use 100 to retain all rendered pixels. `--quality` accepts 1–95; higher values increase file size. Full color resolution (4:4:4) preserves colored text edges. JPEG is lossy, but is encoded only once from the lossless render.

On a sample invitation, 75% and quality 90 reduced a 2.5 MiB PNG to about 400 KiB (84% smaller). Actual size depends on the background and baby photo. Each export reports dimensions and file size. HTML previews stay at the original layout size with embedded assets; share the `.jpg` for the smaller file. No intermediate PNG is saved.

## Edit the design

- `templates/invitation.html`: wording, text placement, sizes, colors, and background styling.
- `examples/names.txt`: fictional starter guest list.
- `generate.py`: batch rendering and command-line options.
- `assets/fonts/`: bundled Berkshire Swash and its SIL Open Font License.

The font is [Berkshire Swash from Google Fonts](https://fonts.google.com/specimen/Berkshire+Swash), sourced from [google/fonts](https://github.com/google/fonts/tree/main/ofl/berkshireswash). Font and background data are embedded in each HTML preview, so rendering needs no network after dependencies and Chromium are installed.

Personal guest lists, the default background file, and rendered output are ignored by Git. Guest names are the primary heading: short names use oversized raspberry lettering, while longer names are fitted by measuring their actual glyph bounds. One- and two-line layouts are compared inside a protected name area, leaving space for ornaments and the sentence below. Extremely long names should be shortened for readability.


## Layout and decorations

The HTML template uses SVG text for the curved headline and precise lettering, with a transparent canvas above it for the flourishes and stars. Everything uses the same 896 × 1184 coordinate system.

- Text stays above y=474 and below y=918, leaving the baby picture area clear.
- All text is centered on the canvas; the upper text may overlap part of the castle. Deep plum (#542451) is used for general text and raspberry (#a82d60) for the guest name and birthday title.
- The template never removes or replaces a red placeholder: use your finished background with the baby picture for final invitations.
- `window.invitationReady` waits for the font, images, name fitting, and canvas drawing. The Python renderer awaits it before exporting.
- Change the SVG coordinates and the canvas drawing calls in `templates/invitation.html` to adjust the composition.

## Gender and ornament font

Guest rows use `Name LastName, F`, `Name LastName, M`, or `Group Name, P` (no header). F produces “Estás invitada al”; M produces “Estás invitado al”; P (plural) produces “Están invitados al”. Whitespace and lowercase gender codes are accepted. Blank lines are skipped; invalid rows report their line number. Quote names containing commas using CSV syntax.

Decorations use filled, tapered canvas flourishes with fuller middles and fine tips, plus uniformly small four-point stars (9 design-pixel radius), in raspberry (#a82d60) to match the guest name. The canvas remains supersampled for crisp exports. Nymphette is retained as an optional asset but is no longer loaded or used by the template. Berkshire Swash remains the lettering font.

Titles such as Tiyo, Tiya, and Tiyos are intentional baby talk and are preserved exactly as written. The F/M/P code controls the invitation wording; titles are never corrected or inferred.

The decoration canvas is composited at 60% opacity (including outlines and stars); text stays fully opaque.

## Resume the latest batch

```sh
uv run python generate.py --background img.png --resume
```

`--resume` reuses the newest timestamp-named release under `--output` (default `output/`). Each input list is checked against its own subfolder and manifest; a newly added list gets a new subfolder in that release. Lists removed from the input folder leave their existing output untouched. Use the same input mode and list filenames when resuming, since renaming a list creates a new group. Each batch includes `manifest.json`, recording the exact name, F/M/P value, and image/HTML filenames for every completed invitation. Resume compares against this manifest, independently of guest-list ordering. Repeated identical rows count as separate invitations.

The command rebuilds the manifest from entries with valid images each time, then saves it atomically after every successful export. Missing or broken images are rendered again under a new number; existing files are never overwritten. Entries for completed guests removed from the input list remain in the manifest because their images remain in the folder. Older folders without a manifest are migrated once from their HTML previews and JPG/PNG files. After migration, matching uses the manifest, so keep it with the images. An invalid manifest reports an error rather than silently discarding it.

If no previous batch exists, a new folder is created. Without `--resume`, every run still creates a new batch and manifest. Use the same background and rendering options when resuming; changing them does not regenerate completed guests. Legacy migration requires the default guest text element and invitation sentence in HTML previews; new batches record manifest entries directly and support custom templates.

## Second render option: Viking invitation with the new time

[View the rendered reference preview](docs/preview-viking.jpg). Its white center is the reserved picture area from the supplied reference.

Use `--layout viking` for the **1136 × 1536** composition matching the supplied `X.jpeg` reference. It reserves the entire central band (y=500–1240) for the picture, with readable cream panels above and below. The reference's white silhouette marks the picture area; use your finished artwork as the background. The renderer does not fill or remove the silhouette.

```sh
uv run python generate.py --layout viking --background backgrounds/X.jpeg
uv run python generate.py --layout viking --background backgrounds/X.jpeg --resume
```

On Windows, the equivalent shortcut is `start-viking.bat --background backgrounds/X.jpeg`. You can pass `--names examples/names.txt` to try the sample guest list, or use the existing `./lists` folder and its independent list subfolders.

The invitation addresses the head of the family and says **“¡Ven con toda tu familia!”** for every F/M/P code. It includes:

- Abi's second birthday, Saturday **October 24, 2026**.
- A prominent **“¡CAMBIO DE HORARIO! Ahora 4:00 p.m.”** banner, with **“Antes 5:00 p.m. · Lo adelantamos por el clima”** below it.
- Calle Arquitectura #419, Ciudad Juárez. The unconfirmed neighborhood name is omitted.
- Clothing size 2 years, warm pajamas and winter clothes; Chimuelo and Teletubbies; lluvia de sobres; guests may bring their own beer.
- Parking in front of the house and more space on Ingeniería beside the park, perpendicular to Arquitectura.
- `xitlaliabigail.com` for more information. This generic printed URL does not replace each family's private RSVP link.

Viking releases are stored under `output/viking/<timestamp>/` (or `<your-output>/viking/`). This keeps `--resume` separate from classic invitations. Defaults produce **1704 × 2304 JPEGs**; use `--size-percent 100` for **2272 × 3072**. Pixel dimensions do not specify a physical paper size or bleed: ask the printer to preserve the aspect ratio and confirm the final trim size.

The original layout remains the default (`--layout classic`), including its original wording and 5 p.m. time. Use **viking** for the updated event information. Edit `templates/invitation_viking.html` for future wording or positioning changes. `--template` still supports custom templates, but cannot be combined with `--layout`. As before, resume does not regenerate completed guests when a background or template changes; omit `--resume` to make a fresh release.
