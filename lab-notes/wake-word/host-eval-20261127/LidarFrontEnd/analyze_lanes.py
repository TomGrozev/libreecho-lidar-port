#!/usr/bin/env python3
"""Per-lane analysis of Lidar 8ch S32 16 kHz tinycap captures.

Reads a WAV (8 ch, S32_LE, 16 kHz), and reports, per lane:
  - DC offset, RMS noise floor (dBFS re int32 full scale and re int16 after >>16)
  - peak, clip counts (int32 rails and int16 rails after >>16)
  - low-byte occupancy (is the word left-justified 24-bit audio?)
  - lane-to-lane correlation
  - spectral tilt: band energies (0-80, 80-300, 300-1k, 1-4k, 4-7.5k, 7.5-8k)
  - energy above 7.6 kHz (aliasing proxy) relative to 1-4 kHz
Also reconstructs micd's mono chain for the default mic mask (0,1,3,4):
  S32>>16 -> mean -> first-order 80 Hz HPF -> 4x digital gain with int16 clamp
and reports level/clipping.
"""
import sys, json
import numpy as np

MASK = [0, 1, 3, 4]

def read_wav(path):
    data = open(path, 'rb').read()
    assert data[:4] == b'RIFF' and data[8:12] == b'WAVE'
    pos = 12
    fmt = None
    while pos + 8 <= len(data):
        cid = data[pos:pos+4]
        sz = int.from_bytes(data[pos+4:pos+8], 'little')
        body = data[pos+8:pos+8+sz]
        if cid == b'fmt ':
            fmt = body
        elif cid == b'data':
            break
        pos += 8 + sz + (sz & 1)
    tag, ch, rate = int.from_bytes(fmt[0:2], 'little'), int.from_bytes(fmt[2:4], 'little'), int.from_bytes(fmt[4:8], 'little')
    bits = int.from_bytes(fmt[14:16], 'little')
    assert tag == 1 and bits == 32 and ch == 8 and rate == 16000, (tag, ch, rate, bits)
    x = np.frombuffer(body, dtype='<i4').reshape(-1, ch)
    return x.astype(np.int64)

def db(x, ref=1.0):
    return 20.0 * np.log10(max(x, 1e-12) / ref)

def band_energy(x, rate, lo, <BT_PEER_NAME_A>):
    # Hann-windowed, averaged periodogram over 2048-sample frames
    n = 2048
    if len(x) < n:
        x = np.pad(x, (0, n - len(x)))
    frames = len(x) // n
    acc = np.zeros(n // 2 + 1)
    win = np.hanning(n)
    for i in range(frames):
        s = x[i*n:(i+1)*n].astype(np.float64)
        s = s - s.mean()
        spec = np.fft.rfft(s * win)
        acc += np.abs(spec) ** 2
    f = np.fft.rfftfreq(n, 1/rate)
    m = (f >= lo) & (f < <BT_PEER_NAME_A>)
    return acc[m].sum() / max(frames, 1) / (n * (win**2).sum() / 2)

def main(path, outdir):
    x = read_wav(path)
    fs = 16000
    n = x.shape[0]
    lanes = x[:, :8]
    s16 = (lanes >> 16).astype(np.int64)   # micd capture_sample(S32) then <<8>>8
    res = {'file': path, 'frames': int(n), 'seconds': n / fs}

    per = []
    for ch in range(8):
        v = lanes[:, ch]
        s = s16[:, ch]
        # low byte occupancy: fraction of samples whose low 8 bits are all 0
        low_zero = float(np.mean((v & 0xFF) == 0))
        low16_zero = float(np.mean((v & 0xFFFF) == 0))
        rms = float(np.sqrt(np.mean(v.astype(np.float64) ** 2)))
        rms16 = float(np.sqrt(np.mean(s.astype(np.float64) ** 2)))
        peak = int(np.max(np.abs(v)))
        peak16 = int(np.max(np.abs(s)))
        clip32 = int(np.sum(np.abs(v) >= (1 << 31) - 1))
        clip16 = int(np.sum(np.abs(s) >= 32767))
        eng = band_energy(v, fs, 0, 4000)
        ali = band_energy(v, fs, 7600, 8000)
        per.append({
            'lane': ch,
            'dc': round(float(np.mean(v)), 1),
            'rms_dbfs_int32': round(db(rms, 2**31), 2),
            'rms_dbfs_int16_equiv': round(db(rms16, 2**15), 2),
            'peak_dbfs_int32': round(db(peak, 2**31), 2),
            'peak16': peak16,
            'clip32': clip32,
            'clip16': clip16,
            'low_byte_zero_frac': round(low_zero, 4),
            'low16_zero_frac': round(low16_zero, 4),
            'band_0_80': round(db(band_energy(v, fs, 0, 80), eng), 1),
            'band_80_300': round(db(band_energy(v, fs, 80, 300), eng), 1),
            'band_300_1k': round(db(band_energy(v, fs, 300, 1000), eng), 1),
            'band_1k_4k': round(db(band_energy(v, fs, 1000, 4000), eng), 1),
            'band_4k_7k5': round(db(band_energy(v, fs, 4000, 7500), eng), 1),
            'band_7k6_8k': round(db(ali, eng), 1),
        })
    res['lanes'] = per

    # correlation matrix of bandpassed-ish (DC removed) lanes
    y = lanes.astype(np.float64)
    y = y - y.mean(axis=0)
    c = np.corrcoef(y.T)
    res['corr'] = [[round(float(c[i, j]), 3) for j in range(8)] for i in range(8)]

    # micd mono chain simulation (mean of mask, HPF, 4x gain)
    mix = np.mean(s16[:, MASK], axis=1)
    k = 31755
    prev_in = 0.0
    prev_out = 0.0
    hp = np.empty_like(mix, dtype=np.float64)
    # vectorised enough in a loop; 1M samples is fine
    for i in range(len(mix)):
        d = prev_out + mix[i] - prev_in
        o = int(d * k / 32768.0)
        prev_in = mix[i]
        prev_out = o
        hp[i] = o
    gained = np.clip(np.trunc(hp * 4.0), -32768, 32767)
    res['mono_chain'] = {
        'pre_gain_rms_int16': round(float(np.sqrt(np.mean(hp**2))), 1),
        'pre_gain_peak': int(np.max(np.abs(hp))),
        'post_gain_rms_int16': round(float(np.sqrt(np.mean(gained**2))), 1),
        'post_gain_peak': int(np.max(np.abs(gained))),
        'post_gain_clipped_samples': int(np.sum(np.abs(gained) >= 32767)),
        'post_gain_rms_dbfs': round(db(float(np.sqrt(np.mean(gained**2))), 32768), 2),
        'post_gain_peak_dbfs': round(db(float(np.max(np.abs(gained))), 32768), 2),
    }
    with open(outdir + '/lanes.json', 'w') as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else '.')
