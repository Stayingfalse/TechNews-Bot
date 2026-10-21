"""Render a spec locally:  python render_cli.py examples/sample_spec.json out.mp4"""
import json
import logging
import sys

from app.render.engine import render_video
from app.spec import StorySpec

logging.basicConfig(level=logging.INFO)
spec = StorySpec.model_validate(json.load(open(sys.argv[1])))
out = sys.argv[2] if len(sys.argv) > 2 else f"out/{spec.id}.mp4"
print(render_video(spec, out, brand="@techdrop.daily", cover_path=out.rsplit(".", 1)[0] + ".jpg"))
