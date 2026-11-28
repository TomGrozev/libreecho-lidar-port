#!/usr/bin/env python3
"""Throwaway microWakeWord comparison harness (pymicro-wakeword, TFLite).

Scores the same clips/conditions as harness.py (openWakeWord pipeline) with the
microWakeWord v2 models, using each model's own manifest cutoff and a loose
cutoff. Outputs JSON to out/mww_*.json.
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H  # noqa: E402  (reuses clip lists and degradations)

from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures  # noqa: E402

MODELS_DIR = os.path.join(HERE, "mww_models")
CALLS = "/home/build/Projects/voice-incubator/tests/adapt_ctc_tests/fixtures/calls"
VPE = "/home/build/Projects/voice-incubator/tests/adapt_ctc_tests/fixtures/audio"
REAL_NABU = [H.REAL_OK, os.path.join(CALLS, "genuine_brightness_fifty.wav"),
             os.path.join(CALLS, "genuine_turn_on_the_lights_nab.wav")]
REAL_ALEXA = [os.path.join(H.FIX, "alexa-twice.wav"), os.path.join(H.FIX, "alexa-what-time.wav")]
PKG_MODELS = os.path.join(HERE, ".mwwvenv/lib/python3.14/site-packages/pymicro_wakeword/models")
LOOSE = 0.5


def load(name, path=None):
    cfg = path or os.path.join(MODELS_DIR, name + ".json")
    return MicroWakeWord.from_config(cfg)


def score(model, samples):
    """Return (probability per inference window, wall seconds)."""
    model.reset()
    feats = MicroWakeWordFeatures()
    probs = []
    t0 = time.perf_counter()
    for frame in feats.process_streaming(samples.astype("<i2").tobytes()):
        p = model.process_streaming_prob(frame)
        probs.append(0.0 if p is None else float(p))
    return probs, time.perf_counter() - t0


def summarize(models, samples):
    xs = H.pad(samples)
    rows = {}
    for name, model, cutoff in models:
        probs, dt = score(model, xs)
        rows[name] = {
            "peak": round(max(probs), 4) if probs else 0.0,
            "peak_t": round((int(np.argmax(probs)) + 1) * 0.03, 2) if probs else 0.0,
            "width_020": sum(1 for p in probs if p >= 0.20),
            "width_thr": sum(1 for p in probs if p >= cutoff),
            "detected": any(p >= cutoff for p in probs),
            "detected_loose": any(p >= LOOSE for p in probs),
            "audio_s": round(len(xs) / H.SR, 2),
            "cpu_s": round(dt, 3),
        }
    return rows


def op_list(path):
    import tflite
    buf = open(path, "rb").read()
    model = tflite.Model.GetRootAsModel(buf, 0)
    names = []
    for i in range(model.OperatorCodesLength()):
        code = model.OperatorCodes(i)
        b = code.BuiltinCode()
        if b == 0:  # BuiltinOperator.PLACEHOLDER_FOR_GREATER_OP_CODES
            b = code.DeprecatedBuiltinCode()
        reverse = {v: k for k, v in vars(tflite.BuiltinOperator).items()
                   if isinstance(v, int)}
        names.append(reverse.get(b, str(b)))
    return sorted(set(names))


def manifest(path):
    d = json.load(open(path))
    return d["micro"]["probability_cutoff"], d["micro"]["sliding_window_size"]


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    outdir = os.path.join(HERE, "out")
    os.makedirs(outdir, exist_ok=True)

    specs = []
    for name in ["okay_nabu", "alexa", "hey_jarvis", "hey_mycroft"]:
        cfg = os.path.join(MODELS_DIR, name + ".json")
        cut, win = manifest(cfg)
        specs.append((name, load(name), cut))
    pkg_cfg = os.path.join(PKG_MODELS, "okay_nabu.json")
    if os.path.exists(pkg_cfg):
        cut, win = manifest(pkg_cfg)
        specs.append(("okay_nabu_pkg", load("okay_nabu", pkg_cfg), cut))

    result = {"loose_cutoff": LOOSE, "models": {}}
    for name, model, cut in specs:
        result["models"][name] = {"cutoff": cut}

    if which in ("all", "ops"):
        ops = {}
        for name in ["okay_nabu", "alexa", "hey_jarvis", "hey_mycroft"]:
            ops[name] = op_list(os.path.join(MODELS_DIR, name + ".tflite"))
        result["ops"] = ops
        print(json.dumps({"ops": ops}))

    sets = {
        "clean": {"ok_nabu": REAL_NABU, "alexa": REAL_ALEXA},
        "reverb_noise": {"ok_nabu": REAL_NABU, "alexa": REAL_ALEXA},
    }

    if which in ("all", "clean"):
        for side, clips in sets["clean"].items():
            rows = []
            for c in clips:
                r = summarize(specs, H.read_wav16(c))
                r["clip"] = os.path.basename(c)
                rows.append(r)
            result.setdefault("clean", {})[side] = rows
            for name, _, cut in specs:
                print(json.dumps({"clean": side, "model": name,
                                  "detect": round(np.mean([x[name]["detected"] for x in rows]), 2),
                                  "detect_loose": round(np.mean([x[name]["detected_loose"] for x in rows]), 2),
                                  "median_peak": round(float(np.median([x[name]["peak"] for x in rows])), 3)}))

    if which in ("all", "degraded"):
        subset = {"ok_nabu": REAL_NABU, "alexa": REAL_ALEXA}
        conds = H.conditions()
        for side, clips in subset.items():
            for cname, fn in conds:
                rows = []
                for c in clips:
                    x = H.read_wav16(c)
                    y = H.far_field(x) if fn is None else fn(x)
                    rows.append(summarize(specs, y))
                ent = {}
                for name, _, cut in specs:
                    ent[name] = {
                        "detect": round(float(np.mean([r[name]["detected"] for r in rows])), 2),
                        "detect_loose": round(float(np.mean([r[name]["detected_loose"] for r in rows])), 2),
                        "median_peak": round(float(np.median([r[name]["peak"] for r in rows])), 3),
                    }
                result.setdefault("degraded", {}).setdefault(side, {})[cname] = ent
                print(json.dumps({"side": side, "cond": cname, **{k: ent[k] for k in ent}}), flush=True)

    if which in ("all", "phase"):
        ph = {}
        for side, clips in {"ok_nabu": REAL_NABU, "alexa": REAL_ALEXA}.items():
            ph[side] = {}
            for c in clips:
                x = H.read_wav16(c)
                acc = {n: {"peaks": [], "hits": 0, "loose": 0} for n in [n for n, _, _ in specs]}
                for off in range(0, H.BLOCK, 80):
                    r = summarize(specs, x)
                    for n in acc:
                        acc[n]["peaks"].append(r[n]["peak"])
                        acc[n]["hits"] += 1 if r[n]["detected"] else 0
                        acc[n]["loose"] += 1 if r[n]["detected_loose"] else 0
                ph[side][os.path.basename(c)] = {
                    n: {"min": round(min(a["peaks"]), 3),
                        "median": round(float(np.median(a["peaks"])), 3),
                        "max": round(max(a["peaks"]), 3),
                        "hit_phases": a["hits"], "hit_phases_loose": a["loose"],
                        "phases": len(a["peaks"])}
                    for n, a in acc.items()}
                print(json.dumps({"phase": side, "clip": os.path.basename(c),
                                  **ph[side][os.path.basename(c)]}), flush=True)
        result["phase"] = ph

    if which in ("all", "neg"):
        calls, vpe = CALLS, VPE
        negs = [os.path.join(H.FIX, f) for f in sorted(os.listdir(H.FIX))
                if f.startswith(("no-wake-word", "music", "pause"))]
        negs += [os.path.join(calls, "false_okay_natalie.wav"),
                 os.path.join(calls, "false_okay_neighbor.wav"),
                 os.path.join(vpe, "vpe_turn_on_the_lights.wav"),
                 os.path.join(vpe, "vpe_turn_all_the_lights.wav"),
                 os.path.join(HERE, "oww_clips/hey_jane.wav")]
        rows = []
        for c in negs:
            try:
                r = summarize(specs, H.read_wav16(c))
            except Exception:
                continue
            r["clip"] = os.path.basename(c)
            rows.append(r)
        result["negatives"] = rows
        for name, _, cut in specs:
            print(json.dumps({"negatives": name, "clips": len(rows),
                              "false_accepts": sum(1 for r in rows if r[name]["detected"]),
                              "false_accepts_loose": sum(1 for r in rows if r[name]["detected_loose"]),
                              "max_peak": round(max(r[name]["peak"] for r in rows), 3)}))

    with open(os.path.join(outdir, "mww_%s.json" % which), "w") as f:
        json.dump(result, f, indent=1)


if __name__ == "__main__":
    main()
