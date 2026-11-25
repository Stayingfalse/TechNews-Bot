"""Render a raosanta.uk promo spec locally: python render_santa.py spec.json out.mp4 [--frames 0,40,90]

No voice-over here (that needs the server's ElevenLabs key and budget). --frames saves those frame
numbers as PNGs next to the video instead of rendering the whole thing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.render.santa.video import Promo, render_promo
from app.santa.spec import PromoSpec


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit(__doc__)
    spec = PromoSpec.model_validate(json.loads(Path(args[0]).read_text()))
    out = Path(args[1])
    if "--frames" in args:
        promo = Promo(spec)
        for f in args[args.index("--frames") + 1].split(","):
            promo.frame(int(f)).convert("RGB").save(out.with_name(f"{out.stem}-{int(f):04d}.png"))
        print(f"{promo.duration:.1f} s, {promo.n_frames} frames")
        return
    print(render_promo(spec, out, cover_path=out.with_suffix(".jpg")))


if __name__ == "__main__":
    main()
