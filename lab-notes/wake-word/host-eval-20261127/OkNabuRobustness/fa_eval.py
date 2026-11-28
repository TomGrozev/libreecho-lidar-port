#!/usr/bin/env python3
"""False-accept evaluation across wake-word models and a big negative pool.

Modes:
  oww  : openWakeWord ONNX packages via harness.EngineStream
  mww  : microWakeWord TFLite models via pymicro-wakeword

Every clip is scored by every model; a model's own wake phrase is excluded from
its negative pool. LibriSpeech dev-clean is reported separately in
false-accepts per hour; the fixture pool in false-accepts per clip.
"""
import json
import os
import subprocess
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H  # noqa: E402

CALLS = "/home/build/Projects/voice-incubator/tests/adapt_ctc_tests/fixtures/calls"
VPE = "/home/build/Projects/voice-incubator/tests/adapt_ctc_tests/fixtures/audio"
CORPUS = "/home/build/Projects/voice-incubator/corpus/positives"
TTS = H.TTS
LS = os.path.join(HERE, "librispeech", "LibriSpeech", "dev-clean")
LS_WAV = os.path.join(HERE, "librispeech", "wav")
LOOSE = 0.5

OWW_MODELS = ["ok_nabu", "alexa", "hey_jarvis", "hey_mycroft"]
MWW_MODELS = ["okay_nabu", "alexa", "hey_jarvis", "hey_mycroft"]


def wav_dur(p):
    with wave.open(p, "rb") as w:
        return w.getnframes() / w.getframerate()


def fixture_pool():
    pool = []  # (path, set of wake words it contains)

    def add(path, words):
        if os.path.exists(path):
            try:
                wav_dur(path)
            except Exception:
                return
            pool.append((path, set(words)))

    # real positives re-declared here (harness.REAL_* are set inside its main)
    def real_nabu():
        return [H.REAL_OK,
                os.path.join(CALLS, "genuine_brightness_fifty.wav"),
                os.path.join(CALLS, "genuine_turn_on_the_lights_nab.wav")]
    for p in real_nabu():
        add(p, ["okay nabu"])
    for f in os.listdir(TTS):
        add(os.path.join(TTS, f), ["okay nabu"] if f.startswith("nabu_") else ["alexa"])
    for p in ["alexa-twice.wav", "alexa-what-time.wav"]:
        add(os.path.join(H.FIX, p), ["alexa"])
    add(os.path.join(HERE, "oww_clips/alexa_test.wav"), ["alexa"])
    add(os.path.join(HERE, "oww_clips/activation16.wav"), [])
    add(os.path.join(HERE, "oww_clips/hey_mycroft_test.wav"), ["hey mycroft"])
    add(os.path.join(HERE, "oww_clips/hey_jane.wav"), ["hey jane"])
    for f in sorted(os.listdir(H.FIX)):
        if f.startswith(("no-wake-word", "music", "pause")):
            add(os.path.join(H.FIX, f), [])
    for p in [os.path.join(VPE, "vpe_turn_on_the_lights.wav"),
              os.path.join(VPE, "vpe_turn_all_the_lights.wav"),
              os.path.join(CALLS, "false_okay_natalie.wav"),
              os.path.join(CALLS, "false_okay_neighbor.wav")]:
        add(p, [])
    for f in sorted(os.listdir(CORPUS)):
        add(os.path.join(CORPUS, f), [])
    return pool


def librispeech_files():
    os.makedirs(LS_WAV, exist_ok=True)
    out = []
    total = 0.0
    for root, _, files in os.walk(LS):
        for f in sorted(files):
            if not f.endswith(".flac"):
                continue
            src = os.path.join(root, f)
            dst = os.path.join(LS_WAV, f[:-5] + ".wav")
            if not os.path.exists(dst):
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-ar", "16000",
                                "-ac", "1", "-sample_fmt", "s16", dst], check=True)
            total += wav_dur(dst)
            out.append(dst)
            if total >= 2100:  # ~35 minutes
                return out, total
    return out, total


def main():
    mode = sys.argv[1]
    out = {"mode": mode, "loose": LOOSE}

    pool = fixture_pool()
    print(json.dumps({"pool_clips": len(pool),
                      "pool_seconds": round(sum(wav_dur(p) for p, _ in pool), 1)}))

    rows = []
    if mode == "oww":
        from wakeword_model import EngineStream
        for p, words in pool:
            xs, sc = H.run_clip(H.read_wav16(p))
            r = {"clip": os.path.basename(p), "words": sorted(words), "sec": round(len(xs) / H.SR, 2)}
            for m in OWW_MODELS:
                ev = H.accept_events(sc[m])
                r[m] = {"peak": round(max(sc[m]), 4), "fa": bool(ev)}
            rows.append(r)
            print(json.dumps(r), flush=True)
    else:
        from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures
        models = {}
        for m in MWW_MODELS:
            models[m] = MicroWakeWord.from_config(os.path.join(HERE, "mww_models", m + ".json"))
        for p, words in pool:
            xs = H.pad(H.read_wav16(p))
            r = {"clip": os.path.basename(p), "words": sorted(words), "sec": round(len(xs) / H.SR, 2)}
            for m, model in models.items():
                model.reset()
                feats = MicroWakeWordFeatures()
                probs = [model.process_streaming_prob(fr) or 0.0
                         for fr in feats.process_streaming(xs.astype("<i2").tobytes())]
                r[m] = {"peak": round(max(probs), 4),
                        "fa": any(q >= model.probability_cutoff for q in probs),
                        "fa_loose": any(q >= LOOSE for q in probs),
                        "cutoff": model.probability_cutoff}
            rows.append(r)
            print(json.dumps(r), flush=True)

    # fixture false accepts: model's own phrase excluded
    words_key = {"ok_nabu": "okay nabu", "okay_nabu": "okay nabu", "alexa": "alexa",
                 "hey_jarvis": "hey jarvis", "hey_mycroft": "hey mycroft"}
    summary = {}
    for m in (OWW_MODELS if mode == "oww" else MWW_MODELS):
        own = words_key[m]
        neg = [r for r in rows if own not in r["words"]]
        key = "fa" if mode == "oww" else "fa"
        loose_key = "fa" if mode == "oww" else "fa_loose"
        summary[m] = {
            "neg_clips": len(neg),
            "fa": sum(1 for r in neg if r[m][key]),
            "fa_loose": sum(1 for r in neg if r[m][loose_key]),
            "max_peak": round(max(r[m]["peak"] for r in neg), 4),
            "fa_clips": [r["clip"] for r in neg if r[m][key]],
        }
    out["fixtures"] = summary
    for m, s in summary.items():
        print(json.dumps({"fixture_summary": m, **{k: v for k, v in s.items() if k != "fa_clips"},
                          "fa_clips": s["fa_clips"][:8]}))

    # LibriSpeech per-hour
    files, total = librispeech_files()
    ls_rows = []
    for p in files:
        if mode == "oww":
            xs, sc = H.run_clip(H.read_wav16(p))
            r = {"clip": os.path.basename(p), "sec": len(xs) / H.SR}
            for m in OWW_MODELS:
                r[m] = bool(H.accept_events(sc[m]))
        else:
            xs = H.pad(H.read_wav16(p))
            r = {"clip": os.path.basename(p), "sec": len(xs) / H.SR}
            for m, model in models.items():
                model.reset()
                feats = MicroWakeWordFeatures()
                probs = [model.process_streaming_prob(fr) or 0.0
                         for fr in feats.process_streaming(xs.astype("<i2").tobytes())]
                r[m] = any(q >= model.probability_cutoff for q in probs)
                r[m + "_loose"] = any(q >= LOOSE for q in probs)
        ls_rows.append(r)
    hours = len(files) and sum(r["sec"] for r in ls_rows) / 3600
    ls_summary = {}
    for m in (OWW_MODELS if mode == "oww" else MWW_MODELS):
        n = sum(1 for r in ls_rows if r[m])
        ls_summary[m] = {"fa": n, "per_hour": round(n / hours, 2) if hours else 0.0}
        if mode == "mww":
            nl = sum(1 for r in ls_rows if r[m + "_loose"])
            ls_summary[m]["per_hour_loose"] = round(nl / hours, 2) if hours else 0.0
    out["librispeech"] = {"files": len(files), "hours": round(hours, 3), "summary": ls_summary}
    print(json.dumps(out["librispeech"]))

    json.dump(out, open(os.path.join(HERE, "out", "fa_%s.json" % mode), "w"), indent=1)


if __name__ == "__main__":
    main()
