#!/usr/bin/env python3
"""
Card Printer UI

Graphical editor for CardPrinter layout files:
- pick the folder that holds the card images
- load / save layout files (InputList.txt format with \newpage markers)
- arrange cards on a live A4 preview (click, drag & drop, add, delete, fill page)
- save the current page preview as a PNG
- export the final PDF using the same engine as the command line tool
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from PIL import Image, ImageDraw, ImageTk

from CardPrinter import CardPrinter, get_images_dict, find_image_match

# Page geometry in cm, must match CardPrinter
PAGE_W_CM, PAGE_H_CM = 21.0, 29.7
CARD_W_CM, CARD_H_CM = 6.3, 9.0
GAP_CM = 0.3
LEFT_CM = 0.75
TOP_CM = 1.05
CUT_LINE_CM = 10 / 28.346  # the PDF cutting lines use a 10 pt stroke width

SLOTS_PER_PAGE = 9


def slot_origin_cm(i):
    """Top-left corner of slot i (0-8) in cm, measured from the page's top-left"""
    row, col = divmod(i, 3)
    return (LEFT_CM + col * (CARD_W_CM + GAP_CM),
            TOP_CM + row * (CARD_H_CM + GAP_CM))


def fit_box(img_w, img_h, box_w, box_h):
    """Size that fits (img_w, img_h) into (box_w, box_h) preserving aspect ratio"""
    scale = min(box_w / img_w, box_h / img_h)
    return max(1, int(img_w * scale)), max(1, int(img_h * scale))


class CardPrinterUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Card Printer")
        self.geometry("1240x900")
        self.minsize(900, 600)

        # Data model: pages is a list of pages, each page a list of 9 slots.
        # A slot is None (empty) or {'name': str, 'path': str or None if missing}.
        self.pages = [self._empty_page()]
        self.cur = 0
        self.sel = None
        self.layout_path = None

        self.image_folder = None
        self.images_dict = {}
        self.images_list = []
        self.filtered_images = []

        self._pil_cache = {}    # path -> downscaled master PIL image
        self._thumb_cache = {}  # (path, w, h) -> PhotoImage
        self._view = None       # (scale, offset_x, offset_y) of the page on the canvas

        self._drag_start = None  # (slot, x, y)
        self._dragging = False
        self._ghost = None
        self._resize_job = None

        self._build_ui()
        self.after(100, self.redraw)

    @staticmethod
    def _empty_page():
        return [None] * SLOTS_PER_PAGE

    # ------------------------------------------------------------------ UI --

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=(6, 6))
        toolbar.pack(side=tk.TOP, fill=tk.X)

        def btn(text, cmd):
            b = ttk.Button(toolbar, text=text, command=cmd)
            b.pack(side=tk.LEFT, padx=2)
            return b

        btn("Image Folder…", self.choose_folder)
        btn("Load Layout…", self.load_layout)
        btn("Save Layout…", self.save_layout)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        btn("Export PDF…", self.export_pdf)
        btn("Save Preview PNG…", self.save_preview)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        btn("◀ Prev", self.prev_page)
        self.page_var = tk.StringVar(value="Page 1 / 1")
        ttk.Label(toolbar, textvariable=self.page_var, width=28,
                  anchor=tk.CENTER).pack(side=tk.LEFT)
        btn("Next ▶", self.next_page)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        btn("+ Add Page", self.add_page)
        btn("Duplicate Page", self.duplicate_page)
        btn("− Delete Page", self.delete_page)

        main = ttk.Frame(self)
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Left panel: image library
        left = ttk.Frame(main, padding=6)
        left.pack(side=tk.LEFT, fill=tk.Y)

        self.folder_var = tk.StringVar(value="No image folder selected")
        ttk.Label(left, textvariable=self.folder_var, wraplength=240).pack(fill=tk.X)

        ttk.Label(left, text="Filter:").pack(anchor=tk.W, pady=(8, 0))
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *a: self.refresh_image_list())
        ttk.Entry(left, textvariable=self.filter_var, width=36).pack(fill=tk.X)

        listframe = ttk.Frame(left)
        listframe.pack(fill=tk.BOTH, expand=True, pady=4)
        self.listbox = tk.Listbox(listframe, width=36, activestyle="dotbox")
        sb = ttk.Scrollbar(listframe, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.LEFT, fill=tk.Y)
        self.listbox.bind("<Double-Button-1>", lambda e: self.place_card())

        ttk.Button(left, text="Place in slot  (double-click)",
                   command=self.place_card).pack(fill=tk.X, pady=1)
        ttk.Button(left, text="Fill whole page with card",
                   command=self.fill_page).pack(fill=tk.X, pady=1)
        ttk.Button(left, text="Remove card from slot  (Del)",
                   command=self.remove_card).pack(fill=tk.X, pady=1)

        # Canvas: A4 page preview
        self.canvas = tk.Canvas(main, bg="gray25", highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Prior>", lambda e: self.prev_page())   # PageUp
        self.canvas.bind("<Next>", lambda e: self.next_page())    # PageDown
        self.bind("<Delete>", lambda e: self.remove_card())

        self.status_var = tk.StringVar(value="Select an image folder to begin.")
        ttk.Label(self, textvariable=self.status_var, padding=(8, 4),
                  relief=tk.SUNKEN).pack(side=tk.BOTTOM, fill=tk.X)

    def status(self, msg):
        self.status_var.set(msg)

    # --------------------------------------------------------- image folder --

    def choose_folder(self, folder=None):
        if folder is None:
            folder = filedialog.askdirectory(title="Select folder with card images")
            if not folder:
                return
        self.image_folder = Path(folder)
        self.images_dict, self.images_list = get_images_dict(folder)
        self.folder_var.set(f"{self.image_folder}  ({len(self.images_list)} images)")
        self.refresh_image_list()
        self._resolve_missing()
        self.redraw()
        self.status(f"Loaded {len(self.images_list)} images from {self.image_folder}")

    def _resolve_missing(self):
        """Try to resolve cards that had no matching image against the new folder"""
        for page in self.pages:
            for card in page:
                if card and not card["path"]:
                    img, _ = find_image_match(card["name"], self.images_dict, self.images_list)
                    if img:
                        card["path"] = str(img)

    def refresh_image_list(self):
        query = self.filter_var.get().strip().lower()
        self.filtered_images = [p for p in self.images_list
                                if query in p.name.lower()]
        self.listbox.delete(0, tk.END)
        for p in self.filtered_images:
            self.listbox.insert(tk.END, p.name)

    def _selected_library_image(self):
        selection = self.listbox.curselection()
        if not selection or not self.filtered_images:
            self.status("Select an image in the list first.")
            return None
        return self.filtered_images[selection[0]]

    # ---------------------------------------------------------- card editing --

    def place_card(self):
        path = self._selected_library_image()
        if not path:
            return
        page = self.pages[self.cur]
        slot = self.sel
        if slot is None:
            slot = next((i for i, c in enumerate(page) if c is None), None)
        if slot is None:
            self.status("Page is full — select a slot to replace, or add a page.")
            return
        page[slot] = {"name": path.name, "path": str(path)}
        self.sel = slot + 1 if slot + 1 < SLOTS_PER_PAGE else slot
        self.redraw()
        self.status(f"Placed {path.name} in slot {slot + 1}")

    def fill_page(self):
        path = self._selected_library_image()
        if not path:
            return
        self.pages[self.cur] = [{"name": path.name, "path": str(path)}
                                for _ in range(SLOTS_PER_PAGE)]
        self.redraw()
        self.status(f"Filled page {self.cur + 1} with {path.name}")

    def remove_card(self):
        if self.sel is None or self.pages[self.cur][self.sel] is None:
            self.status("Select an occupied slot to remove its card.")
            return
        name = self.pages[self.cur][self.sel]["name"]
        self.pages[self.cur][self.sel] = None
        self.redraw()
        self.status(f"Removed {name} from slot {self.sel + 1}")

    # ------------------------------------------------------------- page ops --

    def prev_page(self):
        if self.cur > 0:
            self.cur -= 1
            self.sel = None
            self.redraw()

    def next_page(self):
        if self.cur < len(self.pages) - 1:
            self.cur += 1
            self.sel = None
            self.redraw()

    def add_page(self):
        self.pages.insert(self.cur + 1, self._empty_page())
        self.cur += 1
        self.sel = None
        self.redraw()
        self.status(f"Added empty page {self.cur + 1}")

    def duplicate_page(self):
        copy = [dict(c) if c else None for c in self.pages[self.cur]]
        self.pages.insert(self.cur + 1, copy)
        self.cur += 1
        self.sel = None
        self.redraw()
        self.status(f"Duplicated page as page {self.cur + 1}")

    def delete_page(self):
        if any(self.pages[self.cur]):
            if not messagebox.askyesno("Delete page",
                                       f"Page {self.cur + 1} contains cards. Delete it?"):
                return
        del self.pages[self.cur]
        if not self.pages:
            self.pages = [self._empty_page()]
        self.cur = min(self.cur, len(self.pages) - 1)
        self.sel = None
        self.redraw()
        self.status("Page deleted")

    # ------------------------------------------------------------ load / save --

    def load_layout(self, path=None):
        if path is None:
            path = filedialog.askopenfilename(
                title="Load layout file",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
            if not path:
                return
        path = Path(path)
        if self.image_folder is None:
            # The CLI workflow keeps images next to the layout file
            self.choose_folder(path.parent)

        pages, warnings = self._parse_layout(path)
        if not pages:
            messagebox.showerror("Load layout", "No pages found in the file.")
            return
        self.pages = pages
        self.cur = 0
        self.sel = None
        self.layout_path = path
        self.redraw()
        self.status(f"Loaded {len(pages)} pages from {path.name}")
        if warnings:
            messagebox.showwarning(
                "Load layout",
                "Loaded with issues:\n\n" + "\n".join(warnings[:25])
                + ("\n…" if len(warnings) > 25 else ""))

    def _parse_layout(self, path):
        pages, current, warnings = [], [], []
        with open(path, "r", encoding="utf-8") as f:
            for line_num, raw in enumerate(f, 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line == r"\newpage":
                    if current:
                        pages.append(current)
                        current = []
                    continue
                for name in (n.strip() for n in line.split(",") if n.strip()):
                    img, info = find_image_match(name, self.images_dict, self.images_list)
                    if img:
                        current.append({"name": name, "path": str(img)})
                    else:
                        current.append({"name": name, "path": None})
                        warnings.append(f"Line {line_num}: '{name}' — {info}")
        if current:
            pages.append(current)

        normalized = []
        for i, page in enumerate(pages, 1):
            if len(page) > SLOTS_PER_PAGE:
                warnings.append(f"Page {i} has {len(page)} cards, extra ones dropped")
                page = page[:SLOTS_PER_PAGE]
            page += [None] * (SLOTS_PER_PAGE - len(page))
            normalized.append(page)
        return normalized, warnings

    def save_layout(self, path=None):
        if path is None:
            initial = self.layout_path.name if self.layout_path else "InputList.txt"
            path = filedialog.asksaveasfilename(
                title="Save layout file", defaultextension=".txt",
                initialfile=initial,
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
            if not path:
                return
        path = Path(path)

        incomplete = [str(i + 1) for i, p in enumerate(self.pages)
                      if 0 < sum(1 for c in p if c) < SLOTS_PER_PAGE]
        lines = []
        for i, page in enumerate(self.pages, 1):
            lines.append(f"#{i}")
            names = [c["name"] for c in page if c]
            for j in range(0, len(names), 3):
                chunk = ",".join(names[j:j + 3])
                lines.append(chunk + ("," if j + 3 < len(names) else ""))
            lines.append(r"\newpage")
            lines.append("")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self.layout_path = path
        self.status(f"Saved layout to {path}")
        if incomplete:
            messagebox.showwarning(
                "Save layout",
                "These pages have fewer than 9 cards: " + ", ".join(incomplete)
                + "\nEmpty slots at the end of a page are lost when reloading.")

    # ----------------------------------------------------------------- export --

    def export_pdf(self, path=None):
        if path is None:
            path = filedialog.asksaveasfilename(
                title="Export PDF", defaultextension=".pdf",
                initialfile="cards_output.pdf",
                filetypes=[("PDF files", "*.pdf")])
            if not path:
                return

        missing = sorted({c["name"] for p in self.pages for c in p
                          if c and not c["path"]})
        if missing:
            if not messagebox.askyesno(
                    "Export PDF",
                    "These cards have no matching image and will be left empty:\n\n"
                    + "\n".join(missing[:20])
                    + ("\n…" if len(missing) > 20 else "")
                    + "\n\nExport anyway?"):
                return

        try:
            printer = CardPrinter(str(path))
            printer.start_pdf()
            for page in self.pages:
                printer.create_page_with_images(
                    [c["path"] if c and c["path"] else None for c in page])
            printer.finalize()
        except Exception as e:
            messagebox.showerror("Export PDF", f"Export failed:\n{e}")
            return

        self.status(f"Exported {len(self.pages)} pages to {path}")
        if messagebox.askyesno("Export PDF",
                               f"PDF created:\n{path}\n\nOpen it now?"):
            try:
                os.startfile(path)
            except OSError:
                pass

    def save_preview(self, path=None):
        if path is None:
            path = filedialog.asksaveasfilename(
                title="Save preview image", defaultextension=".png",
                initialfile=f"preview_page_{self.cur + 1}.png",
                filetypes=[("PNG images", "*.png")])
            if not path:
                return
        img = self.render_page_image(self.cur)
        img.save(path)
        self.status(f"Saved preview of page {self.cur + 1} to {path}")

    def render_page_image(self, page_idx, px_per_cm=40):
        """Render one page like the PDF does: background, cutting lines, images"""
        ppc = px_per_cm
        img = Image.new("RGB", (int(PAGE_W_CM * ppc), int(PAGE_H_CM * ppc)), "black")
        draw = ImageDraw.Draw(img)

        if page_idx % 2 == 0:  # odd 1-based page = front with cutting lines
            lw = max(1, round(CUT_LINE_CM * ppc))
            for i in range(SLOTS_PER_PAGE):
                x, y = slot_origin_cm(i)
                draw.rectangle([x * ppc, y * ppc,
                                (x + CARD_W_CM) * ppc, (y + CARD_H_CM) * ppc],
                               outline="white", width=lw)

        for i, card in enumerate(self.pages[page_idx]):
            if not card or not card["path"]:
                continue
            x, y = slot_origin_cm(i)
            box_w, box_h = int(CARD_W_CM * ppc), int(CARD_H_CM * ppc)
            try:
                src = Image.open(card["path"]).convert("RGB")
            except OSError:
                continue
            w, h = fit_box(*src.size, box_w, box_h)
            src = src.resize((w, h), Image.LANCZOS)
            img.paste(src, (int(x * ppc) + (box_w - w) // 2,
                            int(y * ppc) + (box_h - h) // 2))
        return img

    # ----------------------------------------------------------------- canvas --

    def _on_resize(self, _event):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(120, self.redraw)

    def redraw(self):
        self._resize_job = None
        c = self.canvas
        c.delete("all")
        cw, ch = c.winfo_width(), c.winfo_height()
        if cw < 60 or ch < 60:
            return
        scale = min((cw - 24) / PAGE_W_CM, (ch - 24) / PAGE_H_CM)
        ox = (cw - PAGE_W_CM * scale) / 2
        oy = (ch - PAGE_H_CM * scale) / 2
        self._view = (scale, ox, oy)

        c.create_rectangle(ox, oy, ox + PAGE_W_CM * scale, oy + PAGE_H_CM * scale,
                           fill="black", outline="gray60")

        front = (self.cur % 2 == 0)
        if front:
            lw = max(1, round(CUT_LINE_CM * scale))
            for i in range(SLOTS_PER_PAGE):
                x, y = slot_origin_cm(i)
                c.create_rectangle(ox + x * scale, oy + y * scale,
                                   ox + (x + CARD_W_CM) * scale,
                                   oy + (y + CARD_H_CM) * scale,
                                   outline="white", width=lw)

        for i, card in enumerate(self.pages[self.cur]):
            x, y = slot_origin_cm(i)
            x0, y0 = ox + x * scale, oy + y * scale
            x1, y1 = ox + (x + CARD_W_CM) * scale, oy + (y + CARD_H_CM) * scale
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if card and card["path"]:
                photo = self._thumbnail(card["path"], int(x1 - x0), int(y1 - y0))
                if photo:
                    c.create_image(cx, cy, image=photo)
                else:
                    c.create_rectangle(x0, y0, x1, y1, fill="#3a3a3a")
                    c.create_text(cx, cy, text=f"{card['name']}\n(unreadable)",
                                  fill="white", width=x1 - x0 - 8, justify=tk.CENTER)
            elif card:
                c.create_rectangle(x0, y0, x1, y1, fill="#5a1f1f", outline="#aa4444")
                c.create_text(cx, cy, text=f"{card['name']}\n(image missing)",
                              fill="white", width=x1 - x0 - 8, justify=tk.CENTER)
            else:
                c.create_rectangle(x0, y0, x1, y1, outline="gray45", dash=(4, 4))
                c.create_text(cx, cy, text=str(i + 1), fill="gray45",
                              font=("TkDefaultFont", 14))
            if self.sel == i:
                c.create_rectangle(x0, y0, x1, y1, outline="#00c8ff", width=3)

        kind = "front — cutting lines" if front else "back"
        self.page_var.set(f"Page {self.cur + 1} / {len(self.pages)}  ({kind})")

    def _thumbnail(self, path, box_w, box_h):
        key = (path, box_w, box_h)
        if key in self._thumb_cache:
            return self._thumb_cache[key]
        try:
            master = self._pil_cache.get(path)
            if master is None:
                master = Image.open(path).convert("RGB")
                master.thumbnail((800, 800), Image.LANCZOS)
                self._pil_cache[path] = master
            w, h = fit_box(*master.size, box_w, box_h)
            photo = ImageTk.PhotoImage(master.resize((w, h), Image.LANCZOS))
        except OSError:
            return None
        self._thumb_cache[key] = photo
        return photo

    def _slot_at(self, ex, ey):
        if not self._view:
            return None
        scale, ox, oy = self._view
        for i in range(SLOTS_PER_PAGE):
            x, y = slot_origin_cm(i)
            if (ox + x * scale <= ex <= ox + (x + CARD_W_CM) * scale
                    and oy + y * scale <= ey <= oy + (y + CARD_H_CM) * scale):
                return i
        return None

    def _on_press(self, event):
        self.canvas.focus_set()
        slot = self._slot_at(event.x, event.y)
        if slot is not None:
            self.sel = slot
            self.redraw()
        if slot is not None and self.pages[self.cur][slot]:
            self._drag_start = (slot, event.x, event.y)
        else:
            self._drag_start = None
        self._dragging = False

    def _on_motion(self, event):
        if not self._drag_start:
            return
        _, sx, sy = self._drag_start
        if not self._dragging and abs(event.x - sx) + abs(event.y - sy) > 8:
            self._dragging = True
        if self._dragging and self._view:
            if self._ghost:
                self.canvas.delete(self._ghost)
            scale = self._view[0]
            w, h = CARD_W_CM * scale / 3, CARD_H_CM * scale / 3
            self._ghost = self.canvas.create_rectangle(
                event.x - w, event.y - h, event.x + w, event.y + h,
                outline="#00c8ff", width=2, dash=(5, 3))

    def _on_release(self, event):
        if self._ghost:
            self.canvas.delete(self._ghost)
            self._ghost = None
        if self._dragging and self._drag_start:
            src = self._drag_start[0]
            dst = self._slot_at(event.x, event.y)
            if dst is not None and dst != src:
                page = self.pages[self.cur]
                page[src], page[dst] = page[dst], page[src]
                self.sel = dst
                self.redraw()
                self.status(f"Moved card: slot {src + 1} → slot {dst + 1}")
        self._drag_start = None
        self._dragging = False


def main():
    try:  # crisp text on Windows display scaling
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = CardPrinterUI()
    app.mainloop()


if __name__ == "__main__":
    main()
