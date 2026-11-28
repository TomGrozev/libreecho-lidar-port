#!/usr/bin/env python3
"""oWW hey_jarvis / hey_mycroft on the reverb+noise rows (step 3 follow-up).

Positives: real hey_mycroft_test.wav from the openWakeWord repo, plus espeak-ng
synthesis of "hey jarvis" / "hey mycroft" (LABELLED SYNTHETIC - both oWW
classifiers score near zero on espeak, same domain gap as the alexa/ok_nabu
TTS runs, so treat these rows as weak evidence only).
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H  # noqa: E402

POS = {
    "hey_mycroft": [os.path.join(HERE, "oww_clips/hey_mycroft_test.wav"),
                    os.path.join(HERE, "audio/other/hey_mycroft_espeak.wav")],
    "hey_jarvis": [os.path.join(HERE, "audio/other/hey_jarvis_espeak.wav")],
}
NEG = [os.path.join(HERE, "oww_clips/hey_jane.wav"),
       os.path.join(HERE, "oww_clips/alexa_test.wav"),
       os.path.join(H.FIX, "no-wake-word.wav")]


def main():
    conds = [(n, H.far_field if f is None else f) for n, f in H.conditions()
             if n.startswith(("reverb", "noise", "far-field"))]
    conds.append(("clean", lambda x: x))
    out = {}
    for model, clips in POS.items():
        out[model] = {"clips": [os.path.basename(c) for c in clips], "conds": {}}
        for cname, fn in conds:
            rows = []
            for c in clips:
                y = fn(H.read_wav16(c))
                xs, sc = H.run_clip(y)
                rows.append(H.summarize(sc, xs)[model])
            out[model]["conds"][cname] = {
                "detect": round(float(np.mean([r["detected"] for r in rows])), 2),
                "median_peak": round(float(np.median([r["peak"] for r in rows])), 3),
            }
            print(json.dumps({"model": model, "cond": cname,
                              **out[model]["conds"][cname]}), flush=True)
        negrows = []
        for c in NEG:
            xs, sc = H.run_clip(H.read_wav16(c))
            negrows.append(H.summarize(sc, xs)[model])
        out[model]["negatives"] = {
            "clips": [os.path.basename(c) for c in NEG],
            "false_accepts": sum(1 for r in negrows if r["detected"]),
            "max_peak": round(max(r["peak"] for r in negrows), 3),
        }
        print(json.dumps({"model": model, "negatives": out[model]["negatives"]}))
    json.dump(out, open(os.path.join(HERE, "out/oww_other_words.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
