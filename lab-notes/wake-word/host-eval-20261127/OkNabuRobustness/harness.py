#!/usr/bin/env python3
"""Throwaway robustness harness for ok_nabu vs alexa through the device pipeline.

Reuses EngineStream's streaming structure from
work/integration/LibreEcho/tools/wakeword/wakeword_model.py (mirror of
src/adapter/wake_engine_onnx.cpp), but computes mel+embedding features once per
clip and runs every classifier on those identical features, so the comparison
is exact and cheap.

Device accept rule copied from work/integration/LibreEcho-UI/src/adapter/
wake_worker.c:178-290: peak of last 3 block scores >= accept threshold,
>= 2 of the 3 >= 0.20, VAD active at the peak (assumed here), lockout 28000
samples after an event.
"""
import os
import sys
import wave
import json
import numpy as np
import onnxruntime as ort

REPO = "/workspace/libreecho"
sys.path.insert(0, os.path.join(REPO, "work/integration/LibreEcho/tools/wakeword"))
import wakeword_model as wm  # noqa: E402

SENSITIVITY = 82
THRESHOLD = wm.threshold_for(SENSITIVITY)      # 0.4892
SUPPORT = 0.20
LOCKOUT = 28000                                # samples
SR = wm.SAMPLE_RATE
BLOCK = wm.BLOCK_SAMPLES

PKG = os.path.join(REPO, "private/artifacts/wakeword/packages")
MODELS = ["ok_nabu", "alexa", "hey_jarvis", "hey_mycroft"]
FIX = os.path.join(REPO, "work/integration/LibreEcho-UI/tests/voice-e2e/fixtures")
REAL_OK = "/home/build/Projects/voice-incubator/tests/okay_nabu_turn_on_the_lights.wav"
NOISE_WAV = os.path.join(REPO, "private/lab/phase-06/hw-20261121/step31-mic/raw-before.wav")
TTS = os.path.join(REPO, "private/lab/wake-word/host-eval-20261127/OkNabuRobustness/audio/tts")


def read_wav16(path):
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == SR, path
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64)


class FeatureStream:
    """Mirror of EngineStream._process, but keeps one feature vector per block."""

    def __init__(self):
        self.mel = ort.InferenceSession(os.path.join(PKG, MODELS[0], wm.MEL_FILE),
                                        providers=wm.PROVIDERS)
        self.emb = ort.InferenceSession(os.path.join(PKG, MODELS[0], wm.EMBEDDING_FILE),
                                        providers=wm.PROVIDERS)
        self.mel_history = np.ones(wm.MEL_FRAMES * wm.MEL_BINS, np.float32)
        self.feature_history = np.zeros(wm.FEATURE_FRAMES * wm.FEATURE_BINS, np.float32)
        self.feature_count = 0
        self.overlap = np.zeros(0, np.float32)
        for _ in range(wm.PRIMING_BLOCKS):
            self._features(np.zeros(BLOCK, np.int16))
        self.mel_history[:] = 1.0
        self.overlap = np.zeros(0, np.float32)
        self.feature_count = wm.FEATURE_FRAMES

    def _features(self, block):
        audio = np.concatenate([self.overlap, block.astype(np.float32)])
        mel = np.asarray(self.mel.run(None, {wm.MEL_INPUT: audio.reshape(1, -1)})[0],
                         np.float32).reshape(-1)
        frames = mel.size // wm.MEL_BINS
        mel = mel / np.float32(10.0) + np.float32(2.0)
        mh = self.mel_history.reshape(-1, wm.MEL_BINS)
        mel2 = mel.reshape(frames, wm.MEL_BINS)
        if frames >= wm.MEL_FRAMES:
            self.mel_history = mel2[frames - wm.MEL_FRAMES:].reshape(-1).copy()
        else:
            self.mel_history = np.concatenate([self.mel_history[frames * wm.MEL_BINS:],
                                               mel2.reshape(-1)])
        emb = np.asarray(self.emb.run(None, {
            wm.EMBEDDING_INPUT: self.mel_history.reshape(1, wm.MEL_FRAMES, wm.MEL_BINS, 1)})[0],
            np.float32).reshape(-1)
        self.feature_history = np.concatenate([self.feature_history[wm.FEATURE_BINS:], emb])
        if self.feature_count < wm.FEATURE_FRAMES:
            self.feature_count += 1
        self.overlap = block[BLOCK - wm.OVERLAP_SAMPLES:].astype(np.float32)
        return self.feature_history.reshape(1, wm.FEATURE_FRAMES, wm.FEATURE_BINS).copy()

    def blocks(self, samples):
        n = (len(samples) // BLOCK) * BLOCK
        return [self._features(samples[i:i + BLOCK])
                for i in range(0, n, BLOCK)]


def score_all(features):
    """features: list of [1,16,96]; returns {model: [score per block]}."""
    out = {}
    for name in MODELS:
        sess = ort.InferenceSession(os.path.join(PKG, name, wm.CLASSIFIER_FILE),
                                    providers=wm.PROVIDERS)
        key = sess.get_inputs()[0].name
        scores = []
        for fi, f in enumerate(features):
            s = float(np.asarray(sess.run(None, {key: f})[0], np.float32).reshape(-1)[0])
            if fi < wm.STARTUP_SUPPRESSED:
                s = 0.0
            scores.append(s)
        out[name] = scores
    return out


def accept_events(scores):
    """Device rule with VAD assumed active; returns [(block_index, score)]."""
    events = []
    lock = -1
    for i, s in enumerate(scores):
        window = scores[max(0, i - 2):i + 1]
        peak = max(range(len(window)), key=lambda k: window[k])
        peak_score = window[peak]
        support = sum(1 for v in window if v >= SUPPORT)
        if peak_score >= THRESHOLD and support >= 2 and i >= lock:
            events.append((i, peak_score))
            lock = i + int(np.ceil(LOCKOUT / BLOCK))
    return events


def active_rms(x):
    frame = 320
    n = len(x) // frame
    if n == 0:
        return float(np.sqrt(np.mean(x ** 2))) or 1.0
    r = np.sqrt((x[:n * frame].reshape(n, frame) ** 2).mean(axis=1))
    thr = 0.1 * r.max()
    sel = r[r > thr] if (r > thr).any() else r
    return float(np.sqrt((sel ** 2).mean()))


def speech_end(x):
    frame = 320
    n = len(x) // frame
    r = np.sqrt((x[:n * frame].reshape(n, frame) ** 2).mean(axis=1))
    idx = np.where(r > 0.1 * r.max())[0]
    return (idx[-1] + 1) * frame / SR


LEAD = 6 * BLOCK  # preceded by block-aligned silence, like a continuous device stream


def pad(x, offset=0, after=BLOCK):
    return np.concatenate([np.zeros(LEAD + offset), x, np.zeros(after)])


def rir(rt60, drr_db, sr=SR):
    n = int(rt60 * 1.5 * sr)
    t = np.arange(n) / sr
    tail = np.random.RandomState(7).randn(n) * 10 ** (-3 * t / rt60)
    tail[: int(0.005 * sr)] = 0.0
    direct = np.zeros(n)
    d0 = int(0.006 * sr)
    direct[d0] = 1.0
    tgt = 10 ** (-drr_db / 10.0)
    tail *= np.sqrt(tgt / np.sum(tail ** 2))
    h = direct + tail
    return h / np.sqrt(np.sum(h ** 2))


def convolve(x, h):
    n = len(x) + len(h) - 1
    m = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, m) * np.fft.rfft(h, m), m)[:n]
    return y


def load_noise(seconds):
    with wave.open(NOISE_WAV, "rb") as w:
        raw = np.frombuffer(w.readframes(w.getnframes()), dtype="<i4")
        ch = w.getnchannels()
    lane = (raw.reshape(-1, ch)[:, 0] >> 16).astype(np.float64)  # micd.c:990
    n = int(seconds * SR)
    if len(lane) < n:
        lane = np.tile(lane, int(np.ceil(n / len(lane))))
    lane = lane[:n]
    lane -= lane.mean()
    return lane


def apply_gain(x, db):
    return np.clip(x * 10 ** (db / 20.0), -32768, 32767)


def add_noise(x, snr_db, noise):
    s = active_rms(x)
    n = noise[:len(x)]
    n = n / (np.sqrt(np.mean(n ** 2)) or 1.0) * s * 10 ** (-snr_db / 20.0)
    return np.clip(x + n, -32768, 32767)


def conditions():
    conds = []
    for g in [0, -6, -12, -18, -24, -30, -36]:
        conds.append((f"gain {g:+d} dB", lambda x, g=g: apply_gain(x, g)))
    for rt in [0.3, 0.5, 0.8]:
        for drr, label in [(0.0, "1m"), (-9.5, "3m")]:
            h = rir(rt, drr)
            def rev(x, h=h):
                y = convolve(x, h)
                y = y / (active_rms(y) or 1.0) * active_rms(x)
                return np.clip(y, -32768, 32767)
            conds.append((f"reverb RT60 {rt}s DRR {label}", rev))
    for snr in [20, 10, 5]:
        conds.append((f"noise SNR {snr} dB", lambda x, snr=snr: add_noise(x, snr, load_noise(len(x)))))
    conds.append(("far-field RT60 0.5 3m + SNR 10", None))
    return conds


def far_field(x):
    h = rir(0.5, -9.5)
    y = convolve(x, h)
    y = y / (active_rms(y) or 1.0) * active_rms(x)
    return add_noise(np.clip(y, -32768, 32767), 10, load_noise(len(x)))


def run_clip(x, offset=0):
    xs = pad(x, offset)
    feats = FeatureStream().blocks(xs)
    scores = score_all(feats)
    return xs, scores


def summarize(scores, xs):
    rows = {}
    end = speech_end(xs)
    for name, sc in scores.items():
        peak = max(sc) if sc else 0.0
        pi = int(np.argmax(sc)) if sc else 0
        ev = accept_events(sc)
        rows[name] = {
            "peak": round(peak, 4),
            "peak_t": round((pi + 1) * BLOCK / SR, 2),
            "peak_dt_end": round((pi + 1) * BLOCK / SR - end, 2),
            "width_020": sum(1 for s in sc if s >= SUPPORT),
            "width_thr": sum(1 for s in sc if s >= THRESHOLD),
            "detected": len(ev) > 0,
            "events": len(ev),
        }
    return rows


def agg(per_clip, model, key, median=False):
    vals = [c[model][key] for c in per_clip]
    if median:
        return float(np.median(vals))
    return float(np.mean(vals))


MODELS_ORDER = {"ok_nabu": "ok_nabu", "alexa": "alexa"}


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    os.makedirs(outdir, exist_ok=True)

    calls = "/home/build/Projects/voice-incubator/tests/adapt_ctc_tests/fixtures/calls"
    vpe = "/home/build/Projects/voice-incubator/tests/adapt_ctc_tests/fixtures/audio"
    global REAL_NABU, REAL_ALEXA
    REAL_NABU = [REAL_OK,
                 os.path.join(calls, "genuine_brightness_fifty.wav"),
                 os.path.join(calls, "genuine_turn_on_the_lights_nab.wav")]
    REAL_ALEXA = [os.path.join(FIX, "alexa-twice.wav"),
                  os.path.join(FIX, "alexa-what-time.wav")]
    clean_pos = {
        "ok_nabu": list(REAL_NABU) + sorted(
            os.path.join(TTS, f) for f in os.listdir(TTS) if f.startswith("nabu_")),
        "alexa": list(REAL_ALEXA) + sorted(
            os.path.join(TTS, f) for f in os.listdir(TTS) if f.startswith("alexa")),
    }
    clean_pos["ok_nabu_tts"] = clean_pos["ok_nabu"][len(REAL_NABU):]
    clean_pos["alexa_tts"] = clean_pos["alexa"][len(REAL_ALEXA):]

    result = {"threshold": THRESHOLD, "clean": {}, "degraded": {}, "negatives": {}}

    if which in ("all", "clean"):
        for side, clips in clean_pos.items():
            if side.endswith("_tts"):
                continue
            rows = []
            for c in clips:
                xs, sc = run_clip(read_wav16(c))
                r = summarize(sc, xs)
                r["clip"] = os.path.basename(c)
                rows.append(r)
            result["clean"][side] = rows
            print(json.dumps({side: {
                m: {"detect": round(agg(rows, m, "detected"), 3),
                    "median_peak": round(agg(rows, m, "peak", True), 3),
                    "median_width_020": agg(rows, m, "width_020", True),
                    "median_width_thr": agg(rows, m, "width_thr", True),
                    "n": len(rows)}
                for m in MODELS}}))

    subset = {"ok_nabu": list(REAL_NABU), "alexa": list(REAL_ALEXA)}

    if which in ("all", "degraded"):
        conds = conditions()
        for side, clips in subset.items():
            for cname, fn in conds:
                rows = []
                for c in clips:
                    x = read_wav16(c)
                    y = far_field(x) if fn is None else fn(x)
                    xs, sc = run_clip(y)
                    rows.append(summarize(sc, xs))
                result["degraded"].setdefault(side, {})[cname] = {
                    m: {"detect": round(agg(rows, m, "detected"), 2),
                        "median_peak": round(agg(rows, m, "peak", True), 3)}
                    for m in MODELS}
                line = {"side": side, "cond": cname}
                for m in MODELS:
                    line[m] = result["degraded"][side][cname][m]
                print(json.dumps(line), flush=True)

    if which in ("all", "phase"):
        phase_clips = {"ok_nabu": list(REAL_NABU), "alexa": list(REAL_ALEXA)}
        ph = {}
        for side, clips in phase_clips.items():
            ph[side] = {}
            for c in clips:
                x = read_wav16(c)
                peaks = []
                hits = 0
                for off in range(0, BLOCK, 80):
                    xs, sc = run_clip(x, off)
                    peaks.append(max(sc[MODELS_ORDER[side]]))
                    if accept_events(sc[MODELS_ORDER[side]]):
                        hits += 1
                ph[side][os.path.basename(c)] = {
                    "min": round(min(peaks), 3), "median": round(float(np.median(peaks)), 3),
                    "max": round(max(peaks), 3), "hit_phases": hits, "phases": len(peaks)}
                print(json.dumps({"phase": side, "clip": os.path.basename(c),
                                  **ph[side][os.path.basename(c)]}), flush=True)
        result["phase"] = ph

    if which in ("all", "neg"):
        negs = [os.path.join(FIX, f) for f in sorted(os.listdir(FIX))
                if f.startswith(("no-wake-word", "music", "pause"))]
        negs += [os.path.join(calls, "false_okay_natalie.wav"),
                 os.path.join(calls, "false_okay_neighbor.wav"),
                 os.path.join(vpe, "vpe_turn_on_the_lights.wav"),
                 os.path.join(vpe, "vpe_turn_all_the_lights.wav")]
        rows = []
        for c in negs:
            try:
                xs, sc = run_clip(read_wav16(c))
            except Exception:
                continue
            r = summarize(sc, xs)
            r["clip"] = os.path.basename(c)
            rows.append(r)
        result["negatives"] = rows
        for m in MODELS:
            print(json.dumps({"negatives": m,
                              "clips": len(rows),
                              "false_accepts": sum(1 for r in rows if r[m]["detected"]),
                              "max_peak": round(max(r[m]["peak"] for r in rows), 3)}))

    with open(os.path.join(outdir, "results_%s.json" % which), "w") as f:
        json.dump(result, f, indent=1)


if __name__ == "__main__":
    main()
