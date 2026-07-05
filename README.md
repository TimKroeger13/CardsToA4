# CardsToA4 — Card Printer

Creates print-ready A4 PDFs with card images in a 3×3 grid (cards 6.3 cm × 9 cm,
3 mm safety gaps, black background, white cutting lines on the front pages).
Designed for double-sided printing: odd pages are card fronts, even pages are
the matching backs.

## Files

| File               | Purpose                                                        |
|--------------------|----------------------------------------------------------------|
| `CardPrinterUI.py` | Graphical editor + PDF export (the main program)               |
| `CardPrinter.py`   | PDF engine and command line tool (used by the UI)              |
| `InputList.txt`    | Example layout file (`\newpage` separates pages)               |

## Requirements

Python 3.10+ with:

```
pip install reportlab pillow tqdm tkinterdnd2
```

(`tkinterdnd2` is optional — it enables dragging image files in from
Explorer/desktop. The UI runs without it.)

## Running the UI

```
python CardPrinterUI.py
```

Workflow:

1. **Image Folder…** — select the folder containing your card images
   (png/jpg/gif/bmp/tiff). Or skip this: **Load Layout…** automatically uses
   the layout file's folder.
2. **Load Layout…** — open an `InputList.txt`-style file. Cards that can't be
   matched to an image are shown as red *image missing* slots.
3. Edit the pages on the live A4 preview:
   - **Click** a slot to select it.
   - **Drag & drop** a card onto another slot to move it (swaps if occupied).
   - **Double-click** an image in the left list to place it into the selected
     slot (selection then advances to the next slot, so you can fill a page
     by double-clicking nine times).
   - **Fill whole page with card** — puts the selected image in all 9 slots
     (handy for back pages).
   - **Del** key or **Remove card from slot** — clears the selected slot.
   - **Drag files in from Explorer/desktop**: drop image files onto the page
     to place them starting at the slot they land on (or the first empty
     slot); drop them onto the image list to just add them to the library.
     Files from outside the image folder are copied into it automatically so
     saved layouts keep working.
   - **+ Add Page / Duplicate Page / − Delete Page**, **◀ Prev / Next ▶**
     (or PageUp/PageDown) to manage pages.
4. **Save Layout…** — writes the layout back in the same text format, so it
   stays compatible with the command line tool.
5. **Save Preview PNG…** — saves the current page exactly as it will print.
6. **Export PDF…** — creates the PDF with the same engine as the CLI.

Note: page 1, 3, 5, … are fronts and get cutting lines; keep fronts and backs
alternating, and mirror each back row left↔right so backs line up when
printing duplex (flip on long edge).

## Running the command line tool

```
python CardPrinter.py -p InputList.txt          # layout file with \newpage markers
python CardPrinter.py -l cards.txt <folder>     # simple list, one card per line
python CardPrinter.py -b <folder>               # all images, alphabetical
python CardPrinter.py <folder>                  # interactive mode
```

## Layout file format

```
#1                          <- comment lines start with #
1_A,2_A,3_A,                <- card names, comma separated
4_A,6_A,7_A,                   (with or without file extension,
9_A,10_A,12_A                   unique prefixes also work)
\newpage                    <- ends the page (must have exactly 9 cards)
```

## Building a Windows .exe

One-time setup:

```
pip install pyinstaller
```

Build (run inside this folder):

```
pyinstaller --onefile --windowed --name CardPrinter --collect-all tkinterdnd2 CardPrinterUI.py
```

(`--collect-all tkinterdnd2` bundles the drag & drop support library into the
exe; leave it out if you don't have tkinterdnd2 installed.)

- The finished program is **`dist\CardPrinter.exe`** — a single file you can
  copy anywhere; no Python installation needed on the target machine.
- `--windowed` hides the console window. `CardPrinter.py` is bundled
  automatically because the UI imports it.
- Optional: add an icon with `--icon myicon.ico`.
- The `build\` folder and `CardPrinter.spec` file are PyInstaller work files;
  you can delete them after building.

If you also want the command line tool as an exe:

```
pyinstaller --onefile --console --name CardPrinterCLI CardPrinter.py
```

### Troubleshooting

- **Antivirus / SmartScreen warning**: single-file PyInstaller exes are
  sometimes flagged because they self-extract. The exe is safe; add an
  exception, or build without `--onefile` (creates a folder in `dist\`
  instead of a single file, which is flagged less often).
- **Exe starts slowly the first time**: normal for `--onefile` — it unpacks
  itself to a temp folder on launch.
- **Rebuilding after code changes**: just run the same `pyinstaller` command
  again.
