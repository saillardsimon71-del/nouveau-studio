import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.app import media


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    metadata = json.loads((work / "voice-metadata.json").read_text(encoding="utf-8"))
    starts = [0.22, 8.12, 20.10]
    inputs, filters = [], []
    for index, start in enumerate(starts):
        inputs += ["-i", str(work / f"vo-{index+1}.wav")]
        filters.append(f"[{index}:a]atempo=0.96,highpass=f=75,aresample=48000,"
                       f"aformat=channel_layouts=stereo,adelay={int(start*1000)}:all=1[v{index}]")
    filters.append("[v0][v1][v2]amix=inputs=3:normalize=0,apad=whole_dur=26,atrim=duration=26,"
                   "loudnorm=I=-16.5:TP=-3:LRA=7[v]")
    master = work / "vo-master.wav"
    media.run_ffmpeg([*inputs, "-filter_complex", ";".join(filters), "-map", "[v]", "-ar", "48000",
                      "-c:a", "pcm_s16le", str(master)])
    metadata["timeline"] = [{"start_s": start, "duration_s": clip["duration_s"] / 0.96, "text": clip["text"]}
                            for start, clip in zip(starts, metadata["clips"])]
    (work / "voice-timeline.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    import torch
    import whisper

    torch.set_num_threads(6)
    model = whisper.load_model("base", device="cpu", download_root=str(work / "qc-models"))
    audio = whisper.load_audio(str(master))
    aligned = []
    for clip in metadata["timeline"]:
        start = clip["start_s"]
        end = start + clip["duration_s"]
        result = model.transcribe(audio[int(start*16000):int((end+0.08)*16000)], language="fr", fp16=False,
                                  word_timestamps=True, condition_on_previous_text=False,
                                  initial_prompt=clip["text"])
        for segment in result["segments"]:
            segment["start"] += start
            segment["end"] += start
            for word in segment.get("words", []):
                word["start"] += start
                word["end"] += start
        aligned.append({"start_s": start, "expected": clip["text"], "text": result["text"],
                        "segments": result["segments"]})
        print(result["text"], flush=True)
    (work / "voice-asr-aligned.json").write_text(json.dumps(aligned, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
