"""Tiny in-process translation table (English + Georgian).

English is the default. Strings are looked up by key; missing keys fall back
to English, then to the key itself. Kept as a plain dict rather than Qt .ts/.qm
files so contributors can edit translations without the lupdate/lrelease
toolchain.
"""
from __future__ import annotations

LANGUAGES = ("en", "ka")


def _toolkit():
    """The linux-scripts helper (shared language file), when PrintHub runs inside that toolkit; else None."""
    import importlib
    import os
    import sys
    if os.environ.get("PRINTHUB_STANDALONE"):
        return None
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.path.join(here, "..", "..", "common"),               # repository layout
              os.path.join(here, "..", "..", "linux-scripts"),        # <prefix>/lib/printhub + <prefix>/lib/linux-scripts
              "/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts"):
        if os.path.isfile(os.path.join(d, "lscommon.py")):
            if d not in sys.path:
                sys.path.append(d)
            try:
                return importlib.import_module("lscommon")
            except Exception:  # noqa: BLE001 - never let the optional helper break the app
                return None
    return None


def initial_language(saved) -> str:
    """The language PrintHub itself saved; on the very first run the one chosen in the other toolkit apps; else English."""
    if saved in LANGUAGES:
        return saved
    tk = _toolkit()
    try:
        lang = tk.load_lang() if tk else "en"
    except Exception:  # noqa: BLE001
        lang = "en"
    return lang if lang in LANGUAGES else "en"


def share_language(lang: str) -> None:
    """Tell the other toolkit apps which language was picked here (no-op outside the toolkit)."""
    tk = _toolkit()
    try:
        if tk and lang in LANGUAGES:
            tk.save_lang(lang)
    except Exception:  # noqa: BLE001
        pass

TR: dict[str, dict[str, str]] = {
    # window / actions / menu
    "app_subtitle": {"en": "Universal Print", "ka": "უნივერსალური ბეჭდვა"},
    "open": {"en": "Open…", "ka": "გახსნა…"},
    "preview": {"en": "Print Preview", "ka": "წინასწარი ნახვა"},
    "print": {"en": "Print…", "ka": "ბეჭდვა…"},
    "print_all": {"en": "Print All", "ka": "ყველას ბეჭდვა"},
    "menu_view": {"en": "View", "ka": "ხედი"},
    "menu_language": {"en": "Language", "ka": "ენა"},
    "menu_theme": {"en": "Theme", "ka": "თემა"},
    "lang_en": {"en": "English", "ka": "English"},
    "lang_ka": {"en": "ქართული", "ka": "ქართული"},
    "theme_light": {"en": "Light", "ka": "ღია"},
    "theme_dark": {"en": "Dark", "ka": "მუქი"},
    # settings panel
    "settings": {"en": "Print settings", "ka": "ბეჭდვის პარამეტრები"},
    "printer": {"en": "Printer", "ka": "პრინტერი"},
    "resolution": {"en": "Quality (DPI)", "ka": "ხარისხი (DPI)"},
    "no_printer": {"en": "(no printer)", "ka": "(პრინტერი არ არის)"},
    "pages": {"en": "Pages", "ka": "გვერდები"},
    "ph_all": {"en": "all", "ka": "ყველა"},
    "copies": {"en": "Copies", "ka": "ასლები"},
    "collate": {"en": "Collate copies", "ka": "ასლების დახარისხება"},
    "paper_size": {"en": "Paper size", "ka": "ფურცლის ზომა"},
    "orientation": {"en": "Orientation", "ka": "ორიენტაცია"},
    "per_sheet": {"en": "Pages / sheet", "ka": "გვ. / ფურცელზე"},
    "two_sided": {"en": "Two-sided", "ka": "ორმხრივი"},
    "color": {"en": "Color", "ka": "ფერი"},
    "image_scaling": {"en": "Image scaling", "ka": "სურათის მასშტაბი"},
    # combo items
    "dup_off": {"en": "Off", "ka": "გამორთ."},
    "dup_long": {"en": "Long edge", "ka": "გრძელი კიდე"},
    "dup_short": {"en": "Short edge", "ka": "მოკლე კიდე"},
    "col_color": {"en": "Color", "ka": "ფერადი"},
    "col_gray": {"en": "Grayscale", "ka": "შავ-თეთრი"},
    "scale_fit": {"en": "Fit", "ka": "მორგება"},
    "scale_fill": {"en": "Fill", "ka": "შევსება"},
    "scale_actual": {"en": "Actual size", "ka": "რეალური ზომა"},
    "ori_portrait": {"en": "Portrait", "ka": "ვერტიკალ."},
    "ori_landscape": {"en": "Landscape", "ka": "ჰორიზონტ."},
    # photo mode
    "photo_group": {"en": "Photo mode", "ka": "ფოტო-რეჟიმი"},
    "photo_size": {"en": "Print size", "ka": "ბეჭდვის ზომა"},
    "photo_dims": {"en": "Width × height (cm)", "ka": "სიგანე × სიმაღლე (სმ)"},
    "photo_margin": {"en": "Margin (mm)", "ka": "ველი (მმ)"},
    "photo_pos": {"en": "Position", "ka": "მდებარეობა"},
    "ps_fill": {"en": "Fill the paper (edges are cropped)", "ka": "ფურცლის შევსება (კიდეები იჭრება)"},
    "ps_fit": {"en": "Whole photo (white margins)", "ka": "მთელი ფოტო (თეთრი ველებით)"},
    "ps_9x13": {"en": "9 × 13 cm", "ka": "9 × 13 სმ"},
    "ps_10x15": {"en": "10 × 15 cm  (4×6″)", "ka": "10 × 15 სმ  (4×6″)"},
    "ps_13x18": {"en": "13 × 18 cm  (5×7″)", "ka": "13 × 18 სმ  (5×7″)"},
    "ps_15x21": {"en": "15 × 21 cm  (A5)", "ka": "15 × 21 სმ  (A5)"},
    "ps_20x25": {"en": "20 × 25 cm  (8×10″)", "ka": "20 × 25 სმ  (8×10″)"},
    "ps_20x30": {"en": "20 × 30 cm  (8×12″)", "ka": "20 × 30 სმ  (8×12″)"},
    "ps_custom": {"en": "Custom size…", "ka": "საკუთარი ზომა…"},
    "ps_actual": {"en": "Actual size (from the file's dpi)", "ka": "რეალური ზომა (ფაილის dpi-დან)"},
    "pos_center": {"en": "Centre", "ka": "ცენტრი"},
    "pos_top_left": {"en": "Top-left corner", "ka": "ზედა მარცხენა კუთხე"},
    "photo_rotate": {"en": "Turn the photo to suit the paper", "ka": "ფოტოს შემობრუნება ფურცელზე მოსარგებად"},
    "photo_crop": {"en": "Crop the photo to the print size", "ka": "ფოტოს მოჭრა ბეჭდვის ზომაზე"},
    "photo_repeat": {"en": "Fill the sheet with copies", "ka": "ფურცლის შევსება ასლებით"},
    "tt_photo_size": {
        "en": "The paper size above is the print for 'Fill'. For a smaller print on a bigger sheet pick a size here.",
        "ka": "'შევსებისას' ბეჭდვის ზომა ზემოთ არჩეული ფურცლის ზომაა. პატარა ფოტოსთვის დიდ ფურცელზე აირჩიეთ ზომა აქ.",
    },
    "tt_photo_margin": {"en": "Empty border around the photo", "ka": "ცარიელი ველი ფოტოს გარშემო"},
    "tt_photo_rotate": {
        "en": "A landscape photo on portrait paper (or the other way round) is turned instead of cropped or shrunk",
        "ka": "ჰორიზონტალური ფოტო ვერტიკალურ ფურცელზე (და პირიქით) ბრუნდება და არ იჭრება და არ მცირდება",
    },
    "tt_photo_crop": {
        "en": "On: the photo fills the print size and the overflow is cut. Off: the whole photo sits inside it.",
        "ka": "ჩართული: ფოტო ზომას ავსებს და ზედმეტი იჭრება. გამორთული: მთელი ფოტო ზომაში ეტევა.",
    },
    "tt_photo_repeat": {
        "en": "Print as many copies of this size as fit on the sheet (e.g. two 10×15 on an A4)",
        "ka": "დაიბეჭდება ამ ზომის იმდენი ასლი, რამდენიც ფურცელზე ეტევა (მაგ. ორი 10×15 A4-ზე)",
    },
    "photo_na": {"en": "Photo mode works for images - open a photo.", "ka": "ფოტო-რეჟიმი სურათებისთვისაა - გახსენით ფოტო."},
    "photo_size_line": {"en": "Prints at {w} × {h} cm", "ka": "დაიბეჭდება {w} × {h} სმ-ზე"},
    "photo_dpi_good": {"en": "{dpi} dpi - sharp", "ka": "{dpi} dpi - მკვეთრი"},
    "photo_dpi_ok": {"en": "{dpi} dpi - fine for prints", "ka": "{dpi} dpi - ბეჭდვისთვის კარგია"},
    "photo_dpi_low": {"en": "{dpi} dpi - will look soft (small photo or big print)", "ka": "{dpi} dpi - ბუნდოვანი იქნება (პატარა ფოტო ან დიდი ბეჭდვა)"},
    "photo_cropped": {"en": "{pct}% of the photo is cut off at the edges", "ka": "ფოტოს {pct}% კიდეებზე იჭრება"},
    "photo_shrunk": {"en": "That size does not fit the paper - reduced to fit.", "ka": "ეს ზომა ფურცელზე არ ეტევა - შემცირდა."},
    "sent_photo": {"en": "Photo sent to the printer × {c}.", "ka": "ფოტო გაიგზავნა პრინტერზე × {c}."},
    # placeholder
    "placeholder": {
        "en": "Open files  or  drag & drop them here",
        "ka": "გახსენი ფაილები  ან  ჩააგდე აქ",
    },
    "formats": {
        "en": "PDF   ·   PNG / JPG / TIFF   ·   DOCX / XLSX / ODT",
        "ka": "PDF   ·   PNG / JPG / TIFF   ·   DOCX / XLSX / ODT",
    },
    # tooltips
    "tt_pages": {
        "en": "Pages to print, e.g. 1-3, 5, 8-10 (blank = all)",
        "ka": "დასაბეჭდი გვერდები, მაგ. 1-3, 5, 8-10 (ცარიელი = ყველა)",
    },
    "tt_collate": {
        "en": "Print 1,2,3 · 1,2,3 rather than 1,1 · 2,2 · 3,3",
        "ka": "ბეჭდე 1,2,3 · 1,2,3 და არა 1,1 · 2,2 · 3,3",
    },
    "tt_queue": {
        "en": "Files to print (Delete removes the selected one)",
        "ka": "დასაბეჭდი ფაილები (Delete შლის მონიშნულს)",
    },
    "tt_print_all": {"en": "Print the whole queue as one job", "ka": "მთელი რიგი ერთ დავალებად"},
    # status / dialogs
    "ready": {"en": "Ready", "ka": "მზადაა"},
    "loading": {"en": "Loading {name}…", "ka": "{name} იტვირთება…"},
    "loaded": {"en": "{name}  ·  {n} page(s)", "ka": "{name}  ·  {n} გვერდი"},
    "sent": {
        "en": "Sent to printer — {p} page(s), {nup}-up × {c} {cw}.",
        "ka": "გაიგზავნა პრინტერზე — {p} გვერდი, {nup}-up × {c} ასლი.",
    },
    "copy_word": {"en": "copy", "ka": "ასლი"},
    "copies_word": {"en": "copies", "ka": "ასლი"},
    "sent_batch": {
        "en": "Printed {f} file(s), {p} page(s).",
        "ka": "დაიბეჭდა {f} ფაილი, {p} გვერდი.",
    },
    "print_failed": {"en": "Print failed.", "ka": "ბეჭდვა ვერ მოხერხდა."},
    "cannot_open": {"en": "Cannot open", "ka": "ვერ გაიხსნა"},
    "load_failed": {"en": "Failed to load the PDF.", "ka": "PDF ვერ ჩაიტვირთა."},
    "bad_range_title": {"en": "Invalid page range", "ka": "მცდარი გვერდების დიაპაზონი"},
    "bad_range_msg": {
        "en": "Use formats like:  1-3, 5, 8-10\nLeave blank to print all pages.",
        "ka": "გამოიყენე ფორმატი:  1-3, 5, 8-10\nცარიელი = ყველა გვერდი.",
    },
    "no_pages_title": {"en": "No pages selected", "ka": "გვერდები არ არის არჩეული"},
    "no_pages_msg": {
        "en": "That range has no pages in 1–{n}.",
        "ka": "ამ დიაპაზონში 1–{n} გვერდი არ არის.",
    },
    "batch_error": {"en": "Batch error", "ka": "სერიული ბეჭდვის შეცდომა"},
    "nothing_title": {"en": "Nothing to print", "ka": "დასაბეჭდი არაფერია"},
    "nothing_msg": {
        "en": "No pages selected across the queue.",
        "ka": "რიგში არცერთი გვერდი არ არის არჩეული.",
    },
}


class I18n:
    def __init__(self, lang: str = "en") -> None:
        self.lang = lang if lang in LANGUAGES else "en"

    def set_language(self, lang: str) -> None:
        if lang in LANGUAGES:
            self.lang = lang

    def t(self, key: str, **fmt) -> str:
        entry = TR.get(key)
        if not entry:
            return key
        text = entry.get(self.lang) or entry.get("en") or key
        return text.format(**fmt) if fmt else text
