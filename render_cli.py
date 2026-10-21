"""Render a spec locally:  python render_cli.py examples/sample_spec.json out.mp4"""
import json
import logging
import sys
from pathlib import Path

from app.images import fetch_images
from app.render.engine import render_video
from app.spec import StorySpec


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    spec = StorySpec.model_validate(json.load(open(sys.argv[1])))
    out = sys.argv[2] if len(sys.argv) > 2 else f"out/{spec.id}.mp4"
    paths, errors = fetch_images(spec, Path(out).parent / "images")
    if errors:
        print("image errors:", errors)
    cover = out.rsplit(".", 1)[0] + ".jpg"
    print(render_video(spec, out, brand="@techdrop.daily", cover_path=cover, image_paths=paths))


if __name__ == "__main__":  # required: render workers are spawned and re-import this module
    main()
