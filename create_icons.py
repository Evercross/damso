"""
Damso — App icon generator.

Design "A2": cream background + coral speech bubble + cream mic inside.
Generates app icons (128/256/512) and menu bar template icons (1x/2x).
All shapes are drawn at 4x supersampling and downscaled for smooth edges.
"""
from PIL import Image, ImageDraw
import os

ICON_DIR = os.path.dirname(os.path.abspath(__file__))

CREAM = (255, 241, 226, 255)      # #FFF1E2 background
CORAL = (255, 107, 94, 255)       # #FF6B5E speech bubble
CORAL_SOFT = (255, 107, 94, 185)  # smile accent
WHITE = (255, 255, 255, 230)      # menu bar template fill
CLEAR = (0, 0, 0, 0)


def _draw_bubble_mic(d: ImageDraw.ImageDraw, s: float, bubble, mic) -> None:
    """Draw a speech bubble with a microphone cut into it.

    s: scale factor relative to the 512 reference canvas.
    bubble/mic: fill colors. Mic is drawn with raw pixel writes, so passing
    CLEAR erases through the bubble (used for the menu bar template icon).
    """
    def r(*vals):
        return [v * s for v in vals]

    # Speech bubble body + tail
    d.rounded_rectangle(r(119, 68, 392, 293), radius=68 * s, fill=bubble)
    d.polygon(r(160, 280, 258, 280, 160, 368), fill=bubble)

    # Microphone (capsule + cradle arc + stem)
    d.rounded_rectangle(r(229, 130, 283, 218), radius=27 * s, fill=mic)
    d.arc(r(203, 140, 309, 246), start=0, end=180, fill=mic, width=int(16 * s))
    d.rounded_rectangle(r(248, 244, 264, 272), radius=8 * s, fill=mic)


def create_app_icon(size: int) -> str:
    """Create the A2 app icon at the given size."""
    ss = 4
    c = 512 * ss
    img = Image.new("RGBA", (c, c), CLEAR)
    d = ImageDraw.Draw(img)

    # macOS-style rounded square background (~22.5% corner radius)
    d.rounded_rectangle([0, 0, c - 1, c - 1], radius=int(c * 0.225), fill=CREAM)
    _draw_bubble_mic(d, ss, bubble=CORAL, mic=CREAM)

    # Smile accent under the bubble
    d.arc([177 * ss, 380 * ss, 334 * ss, 470 * ss], start=20, end=160,
          fill=CORAL_SOFT, width=int(17 * ss))

    img = img.resize((size, size), Image.LANCZOS)
    path = os.path.join(ICON_DIR, f"icon_app_{size}.png")
    img.save(path)
    print(f"App icon {size}px: {path}")
    return path


def create_menubar_icon(size: int, suffix: str = "") -> str:
    """Create the menu bar template icon: white bubble, mic punched out."""
    ss = 8
    c = 512 * ss // 1
    img = Image.new("RGBA", (c, c), CLEAR)
    d = ImageDraw.Draw(img)

    # Bubble fills most of the canvas; CLEAR mic erases pixels (no blending)
    _draw_bubble_mic(d, ss * 512 / 512, bubble=WHITE, mic=CLEAR)

    # Crop to bubble bounds (plus tail) so the glyph fills the small canvas
    img = img.crop((100 * ss, 50 * ss, 410 * ss, 386 * ss))
    img = img.resize((size, size), Image.LANCZOS)
    path = os.path.join(ICON_DIR, f"icon_menubar{suffix}.png")
    img.save(path)
    print(f"Menu bar icon {size}px: {path}")
    return path


if __name__ == "__main__":
    for s in (128, 256, 512):
        create_app_icon(s)
    create_menubar_icon(22)
    create_menubar_icon(44, "@2x")
    print("Done.")
