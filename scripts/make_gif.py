"""Stitch the captured screenshots into a product-tour GIF for the README."""

from pathlib import Path

from PIL import Image

SHOTS = Path("/shots")
frames = sorted(SHOTS.glob("0*.png"))
if not frames:
    raise SystemExit("no screenshots found")

imgs = [
    Image.open(f)
    .resize((1200, 675), Image.LANCZOS)
    .quantize(colors=160, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
    for f in frames
]

imgs[0].save(
    SHOTS / "adjutant-tour.gif",
    save_all=True,
    append_images=imgs[1:],
    duration=2800,
    loop=0,
    optimize=True,
)
print(f"adjutant-tour.gif written from {len(imgs)} frames")
