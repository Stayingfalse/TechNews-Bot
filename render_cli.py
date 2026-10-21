"""Render a quiz locally:  python render_cli.py examples/sample_quiz.json out/sample.mp4 [music_dir]"""
import json
import logging
import sys
from pathlib import Path

from app.render.engine import render_video
from app.spec import QuizSpec


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    spec = QuizSpec.model_validate(json.load(open(sys.argv[1])))
    out = sys.argv[2] if len(sys.argv) > 2 else f"out/{spec.id}.mp4"
    music_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("music")
    cover = out.rsplit(".", 1)[0] + ".jpg"
    print(render_video(spec, out, brand="@quizdrop.daily", cover_path=cover, music_dir=music_dir))


if __name__ == "__main__":  # required: render workers are spawned and re-import this module
    main()
