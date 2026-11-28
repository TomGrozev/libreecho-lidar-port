#!/usr/bin/env python3
"""Host replay of the lab clips through the waked decode path (ticket 03).

Builds a throwaway binary from the LibreEcho-UI topic branch that links the
real wake_worker.c and the real microWakeWord engine with TFLite Micro, feeds
each lab clip, and compares the detections against the pymicro-wakeword
reference in ../host-eval-20261127/OkNabuRobustness/out/mww_clean.json.

usage: run.py [--branch DIR] [--models DIR] [--tflm DIR]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "/workspace/libreecho"
EVAL = os.path.join(REPO, "private/lab/wake-word/host-eval-20261127/OkNabuRobustness")
REFERENCE = os.path.join(EVAL, "out/mww_clean.json")
FIX = os.path.join(REPO, "work/integration/LibreEcho-UI/tests/voice-e2e/fixtures")
CALLS = "/home/build/Projects/voice-incubator/tests/adapt_ctc_tests/fixtures/calls"

# The clean set of mww_clean.json, clip -> word that must fire.
CLIPS = [
    ("alexa", os.path.join(FIX, "alexa-twice.wav")),
    ("alexa", os.path.join(FIX, "alexa-what-time.wav")),
    ("okay_nabu", "/home/build/Projects/voice-incubator/tests/okay_nabu_turn_on_the_lights.wav"),
    ("okay_nabu", os.path.join(CALLS, "genuine_brightness_fifty.wav")),
    ("okay_nabu", os.path.join(CALLS, "genuine_turn_on_the_lights_nab.wav")),
]


def raw_pcm(path, out):
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
        assert w.getframerate() == 16000, path
        open(out, "wb").write(w.readframes(w.getnframes()))


def build(args, work):
    branch = args.branch
    cflags = ["-D_POSIX_C_SOURCE=200809L", "-std=c99", "-O2", "-Wall", "-Wextra",
              "-Wpedantic", "-Werror", f"-I{branch}/src", f"-I{branch}/src/adapter",
              "-DLE_WAKE_ENGINE_MWW"]
    cxxflags = ["-std=c++17", "-O2", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                f"-I{branch}/src", f"-I{branch}/src/adapter"]
    objects = []
    for src in ("src/adapter/wake_worker.c", "src/json.c", "src/wake_model.c"):
        obj = os.path.join(work, os.path.basename(src) + ".o")
        subprocess.run(["cc", *cflags, "-c", os.path.join(branch, src), "-o", obj],
                       check=True)
        objects.append(obj)
    for src in ("src/adapter/wake_engine_mww.cpp",):
        obj = os.path.join(work, os.path.basename(src) + ".o")
        subprocess.run(["c++", *cxxflags, f"-isystem{args.tflm}/include",
                        "-c", os.path.join(branch, src), "-o", obj], check=True)
        objects.append(obj)
    cobj = os.path.join(work, "replay.o")
    subprocess.run(["cc", *cflags, "-c", os.path.join(HERE, "replay.c"), "-o", cobj],
                   check=True)
    objects.append(cobj)
    binary = os.path.join(work, "replay")
    subprocess.run(["c++", *objects, os.path.join(args.tflm, "lib/libtflm-micro.a"),
                    os.path.join(args.tflm, "lib/libmicrowakeword-frontend.a"),
                    "-lpthread", "-lm", "-o", binary], check=True)
    return binary


def expected_detection(reference, clip, word):
    for rows in reference["clean"].values():
        for row in rows:
            if row["clip"] == os.path.basename(clip):
                return bool(row[word]["detected"])
    return None


def models_dir(root, models):
    for name in ("alexa", "okay_nabu", "vad"):
        target = os.path.join(root, "wakeword-models", name)
        os.makedirs(target, exist_ok=True)
        for ext in (".tflite", ".json"):
            shutil.copy(os.path.join(models, name + ext), target)
    return os.path.join(root, "wakeword-models")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", default=os.path.join(
        REPO, "work/topic/03-LibreEcho-UI"))
    parser.add_argument("--models", default=os.path.join(
        REPO, "work/inputs/public-deps/micro-wake-word-models-source/models/v2"))
    parser.add_argument("--tflm", default=os.path.join(
        REPO, "work/inputs/tmp/mww-host"))
    args = parser.parse_args()

    reference = json.load(open(REFERENCE))
    with tempfile.TemporaryDirectory(prefix="wake-replay-") as work:
        binary = build(args, work)
        roots = models_dir(work, args.models)
        failures = 0
        runs = 0
        for _, clip in CLIPS:
            pcm = os.path.join(work, "clip.pcm")
            raw_pcm(clip, pcm)
            for word in ("alexa", "okay_nabu"):
                runs += 1
                out = subprocess.run([binary, os.path.join(roots, word), pcm],
                                     capture_output=True, text=True, timeout=120)
                print(f"--- {os.path.basename(clip)} [{word}]\n{out.stdout}"
                      f"{out.stderr}", end="")
                summary = [l for l in out.stdout.splitlines()
                           if l.startswith("detections")]
                detections = int(summary[0].split()[1]) if summary else 0
                expected = expected_detection(reference, clip, word)
                print(f"result: {'detected' if detections else 'missed'} "
                      f"(reference {'detected' if expected else 'missed'}), "
                      f"exit={out.returncode}")
                failures += (detections > 0) != expected or out.returncode != 0
    print(f"{runs - failures}/{runs} clip/model pairs match the reference")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
