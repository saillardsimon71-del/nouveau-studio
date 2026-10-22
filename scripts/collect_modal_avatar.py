"""Retrieve an already completed Modal call without spawning another GPU."""
import argparse
import base64
import json
import re
from pathlib import Path

import modal

parser = argparse.ArgumentParser()
parser.add_argument("call_id")
parser.add_argument("--out", default="artifacts/longcat_avatar_fr.mp4")
args = parser.parse_args()
if not re.fullmatch(r"fc-[A-Za-z0-9]+", args.call_id):
    raise SystemExit("Invalid Modal function call id")
if modal.Workspace.from_context().hydrate().name != "kulejean567":
    raise SystemExit("Expected Modal workspace kulejean567")
result = modal.FunctionCall.from_id(args.call_id).get(timeout=60)
metadata = result["metadata"]
if metadata["engine"] != "longcat-video-avatar-1.5":
    raise SystemExit("This is not a LongCat avatar result")
tracks = metadata["streams"]
if not any(s["codec_type"] == "audio" for s in tracks):
    raise SystemExit("Avatar has no audio track")
if not any(s.get("width") == 720 and s.get("height") == 1280 for s in tracks):
    raise SystemExit("Avatar is not vertical 720x1280")
path = Path(args.out)
path.parent.mkdir(parents=True, exist_ok=True)
path.write_bytes(base64.b64decode(result["video_b64"], validate=True))
path.with_suffix(".json").write_text(json.dumps({**metadata, "modal_call_id": args.call_id}, indent=2), encoding="utf-8")
print(f"Retrieved real MP4: {path.stat().st_size} bytes; no GPU call spawned")
