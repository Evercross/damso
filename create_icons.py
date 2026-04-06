"""
Damso — Create cute app icons.
Generates menu bar icon (small) and app icon (large).
"""
from PIL import Image, ImageDraw, ImageFont
import os

ICON_DIR = os.path.dirname(os.path.abspath(__file__))


def create_menubar_icon(size=22):
    """Create a small menu bar icon — simple cute microphone."""
    # Menu bar icons should be template images (white on transparent)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    cx = size // 2
    # Mic head (rounded rect approximated by ellipse)
    d.ellipse([cx-4, 2, cx+4, 11], fill=(255, 255, 255, 230))
    # Mic body/stem
    d.rectangle([cx-1, 11, cx+1, 16], fill=(255, 255, 255, 230))
    # Mic base arc
    d.arc([cx-6, 7, cx+6, 17], start=0, end=180, fill=(255, 255, 255, 200), width=1)
    # Base line
    d.rectangle([cx-3, 17, cx+3, 18], fill=(255, 255, 255, 200))

    path = os.path.join(ICON_DIR, "icon_menubar.png")
    img.save(path)
    print(f"Menu bar icon: {path}")

    # Also save @2x version
    img2x = create_menubar_icon_2x(size * 2)
    path2x = os.path.join(ICON_DIR, "icon_menubar@2x.png")
    img2x.save(path2x)
    print(f"Menu bar icon @2x: {path2x}")
    return path


def create_menubar_icon_2x(size=44):
    """Create @2x retina menu bar icon."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    cx = size // 2
    # Mic head
    d.ellipse([cx-8, 4, cx+8, 22], fill=(255, 255, 255, 230))
    # Stem
    d.rectangle([cx-2, 22, cx+2, 32], fill=(255, 255, 255, 230))
    # Arc
    d.arc([cx-12, 14, cx+12, 34], start=0, end=180, fill=(255, 255, 255, 200), width=2)
    # Base
    d.rectangle([cx-6, 34, cx+6, 36], fill=(255, 255, 255, 200))
    return img


def create_app_icon(size=512):
    """Create a cute app icon with gradient background and mic emoji style."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded rectangle background with gradient
    margin = int(size * 0.05)
    radius = int(size * 0.22)

    # Create gradient background
    for y in range(margin, size - margin):
        ratio = (y - margin) / (size - 2 * margin)
        r = int(108 * (1 - ratio) + 232 * ratio)  # Purple to pink
        g = int(92 * (1 - ratio) + 67 * ratio)
        b = int(231 * (1 - ratio) + 147 * ratio)
        d.line([(margin, y), (size - margin, y)], fill=(r, g, b, 255))

    # Create rounded rectangle mask
    mask = Image.new("L", (size, size), 0)
    mask_d = ImageDraw.Draw(mask)
    mask_d.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius,
        fill=255,
    )
    img.putalpha(mask)

    # Re-draw on masked image
    d = ImageDraw.Draw(img)

    # Microphone body (cute rounded shape)
    cx, cy = size // 2, int(size * 0.38)
    mic_w = int(size * 0.18)
    mic_h = int(size * 0.28)

    # Mic head — white rounded capsule
    d.rounded_rectangle(
        [cx - mic_w, cy - mic_h, cx + mic_w, cy + mic_h],
        radius=mic_w,
        fill=(255, 255, 255, 240),
    )

    # Mic grille lines
    for i in range(3):
        ly = cy - mic_h + int(mic_h * 0.6) + i * int(mic_h * 0.25)
        d.line(
            [(cx - mic_w + 12, ly), (cx + mic_w - 12, ly)],
            fill=(200, 180, 220, 100),
            width=max(2, size // 128),
        )

    # Mic stand arc
    arc_y = cy + mic_h
    arc_w = int(size * 0.22)
    d.arc(
        [cx - arc_w, arc_y - int(size * 0.08), cx + arc_w, arc_y + int(size * 0.18)],
        start=0,
        end=180,
        fill=(255, 255, 255, 200),
        width=max(4, size // 64),
    )

    # Mic stem
    stem_top = arc_y + int(size * 0.05)
    stem_bottom = stem_top + int(size * 0.12)
    stem_w = max(3, size // 80)
    d.rectangle(
        [cx - stem_w, stem_top, cx + stem_w, stem_bottom],
        fill=(255, 255, 255, 220),
    )

    # Base
    base_w = int(size * 0.12)
    base_h = max(4, size // 64)
    d.rounded_rectangle(
        [cx - base_w, stem_bottom, cx + base_w, stem_bottom + base_h],
        radius=base_h // 2,
        fill=(255, 255, 255, 220),
    )

    # Sound waves (cute circles)
    wave_cx = cx + int(size * 0.22)
    wave_cy = cy - int(size * 0.05)
    for i, offset in enumerate([0, 18, 36]):
        alpha = 180 - i * 50
        r = int(size * 0.04) + i * int(size * 0.03)
        d.arc(
            [wave_cx - r + offset // 2, wave_cy - r, wave_cx + r + offset // 2, wave_cy + r],
            start=-60,
            end=60,
            fill=(255, 255, 255, max(alpha, 60)),
            width=max(3, size // 100),
        )

    # Save app icon at multiple sizes
    path_512 = os.path.join(ICON_DIR, "icon_app_512.png")
    img.save(path_512)
    print(f"App icon 512: {path_512}")

    path_256 = os.path.join(ICON_DIR, "icon_app_256.png")
    img.resize((256, 256), Image.LANCZOS).save(path_256)

    path_128 = os.path.join(ICON_DIR, "icon_app_128.png")
    img.resize((128, 128), Image.LANCZOS).save(path_128)

    # Create .icns for macOS .app bundle
    create_icns(img)
    return path_512


def create_icns(img_512):
    """Create macOS .icns file from a 512x512 image."""
    iconset_dir = os.path.join(ICON_DIR, "Damso.iconset")
    os.makedirs(iconset_dir, exist_ok=True)

    sizes = [16, 32, 64, 128, 256, 512]
    for s in sizes:
        resized = img_512.resize((s, s), Image.LANCZOS)
        resized.save(os.path.join(iconset_dir, f"icon_{s}x{s}.png"))
        # @2x versions
        if s <= 256:
            resized2x = img_512.resize((s * 2, s * 2), Image.LANCZOS)
            resized2x.save(os.path.join(iconset_dir, f"icon_{s}x{s}@2x.png"))

    # Convert iconset to icns using iconutil
    icns_path = os.path.join(ICON_DIR, "Damso.icns")
    os.system(f'iconutil -c icns "{iconset_dir}" -o "{icns_path}"')
    print(f"App icon .icns: {icns_path}")

    # Cleanup iconset
    import shutil
    shutil.rmtree(iconset_dir, ignore_errors=True)
    return icns_path


if __name__ == "__main__":
    print("Creating Damso icons...")
    create_menubar_icon()
    create_app_icon()
    print("Done!")
