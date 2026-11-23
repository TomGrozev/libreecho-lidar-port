#!/usr/bin/env python3
"""Run the stock Sendspin outer-loop harness's rtstart scenario per target.

Throwaway probe: compiles the real audio_engine.c (read-only, from the
LibreEcho-Platform checkout) against the harness's fake TinyALSA PCM, and
runs the same rtstart scenario under each rendered target speaker profile.
The Lidar profile forces playback_format=s16_le, so the engine opens the
2048x2 = 4096-frame S16 ring; Radar/Dot open the 1024x3 = 3072-frame S32 ring.

The target table in this checkout has no 'lidar' entry, so its identity and
profile are taken verbatim from test_audio_engine_contract.py's LIDAR_PROFILE
(renderer fixture), which is the only Lidar profile in the tree.

Only the harness copy (LOOP_PROGRAM) is patched: credited frames, underruns
and the pcm avail distribution seen by pcm_get_htimestamp are printed; the
engine source is untouched.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
AIRPLAY = HERE.parents[3] / "forks/LibreEcho-Platform/tools/mt8163-arm32/airplay"
sys.path.insert(0, str(AIRPLAY))
import test_audio_engine_sendspin as T  # noqa: E402

assert T.SOURCE_DIR == AIRPLAY

LIDAR_IDENTITY = b"target_id=lidar\nrelease_slug=lidar\nhw_profile=lidar@0\n"
LIDAR_PROFILE = (
    "schema=1\ntarget_id=lidar\nspeaker_chain=lidar\ncodec_profile=Flat\n"
    "hp_driver_gain=6\npre_gain_db=0.00\nbass_makeup_db=0.00\nlo_driver_gain=6\n"
    "playback_card=0\nplayback_device=0\nplayback_rate=48000\n"
    "playback_channels=2\nplayback_format=s16_le\n"
).encode()

src = T.LOOP_PROGRAM
src = src.replace(
    '        check(ok, "rtstart: the engine stopped crediting a fed generation (XRUN fence?)");',
    '        fprintf(stderr, "rtstart: credited %llu frames in %.2f s over %u DATA offers\\n",\n'
    '                (unsigned long long)first, mono_seconds() - start, (unsigned)seq);\n'
    '        check(ok, "rtstart: the engine stopped crediting a fed generation (XRUN fence?)");',
)
src = src.replace(
    "    if (g_log.rt_underruns)\n"
    '        fprintf(stderr, "rtstart: %u underrun(s)\\n", (unsigned)g_log.rt_underruns);',
    "    if (g_log.rt_underruns)\n"
    '        fprintf(stderr, "rtstart: %u underrun(s)\\n", (unsigned)g_log.rt_underruns);',
)
src = src.replace(
    "    (void)run_engine(root, 0u, 23u);\n    dump_log(root, 0);",
    "    (void)run_engine(root, 0u, 23u);\n"
    "    if (g_scen == SCEN_RTSTART)\n"
    '        fprintf(stderr, "rtstart: hts ALL %u, >=PERIOD %u (immediate return), "\n'
    '                "<PERIOD %u (bridge polls), min avail %u, pcm writes %u\\n",\n'
    "                g_hts_any, g_hts_large, g_hts_small,\n"
    "                g_hts_min == 1000000u ? 0u : g_hts_min, g_write_calls);\n"
    "    dump_log(root, 0);",
)
src = src.replace(
    "static unsigned int rt_queued(struct pcm *pcm, const struct timespec *now)",
    "static unsigned g_hts_calls, g_hts_small, g_hts_large, g_hts_min = 1000000u;\n"
    "static unsigned g_hts_any;\n\n"
    "static unsigned int rt_queued(struct pcm *pcm, const struct timespec *now)",
)
src = src.replace(
    "                       struct timespec *timestamp)\n{\n    (void)pcm;",
    "                       struct timespec *timestamp)\n{\n    (void)pcm;\n"
    "    g_hts_any += 1u;",
)
src = src.replace(
    "        *avail = pcm->buffer_frames - rt_queued(pcm, timestamp);\n        return 0;",
    "        *avail = pcm->buffer_frames - rt_queued(pcm, timestamp);\n"
    "        if (g_scen == SCEN_RTSTART) {\n"
    "            g_hts_calls += 1u;\n"
    "            if (*avail < g_hts_min) g_hts_min = *avail;\n"
    "            if (*avail < PERIOD_SIZE) g_hts_small += 1u;\n"
    "            else g_hts_large += 1u;\n"
    "        }\n        return 0;",
)
src = src.replace(
    "    C_HPRIN1, C_HPGAIN, C_PCMVOL, C_COUNT",
    "    C_HPRIN1, C_HPGAIN, C_PCMVOL, C_LODAC, C_LOGAIN, C_LOLMIX, C_LORMIX,\n"
    "    C_DACMONO, C_ROUTE, C_COUNT",
)
src = src.replace(
    '    "PCM Playback Volume"\n};',
    '    "PCM Playback Volume", "LO DAC Playback Switch", "LO Driver Gain Volume",\n'
    '    "LOL Output Mixer L_DAC Switch", "LOR Output Mixer R_DAC Switch",\n'
    '    "DAC Mono Mix Switch", "Output Route"\n};',
)
src = src.replace(
    "    if (idx == C_HPDAC || idx == C_HPGAIN || idx == C_PCMVOL)\n        return 2;",
    "    if (idx == C_HPDAC || idx == C_HPGAIN || idx == C_PCMVOL ||\n"
    "        idx == C_LODAC || idx == C_LOGAIN)\n        return 2;",
)
src = src.replace(
    '    else if (strcmp(value, "Stereo") == 0) code = 2u;',
    '    else if (strcmp(value, "Stereo") == 0) code = 2u;\n'
    '    else if (strcmp(value, "Speaker") == 0) code = 3u;\n'
    '    else if (strcmp(value, "Line Out") == 0) code = 4u;',
)
for needle in ("credited %llu frames", "hts ALL %u", "g_hts_calls += 1u",
               "g_hts_any += 1u", "g_hts_large += 1u", "C_DACMONO",
               'idx == C_LOGAIN', '"Line Out") == 0) code = 4u'):
    assert needle in src, needle
T.LOOP_PROGRAM = src

base_tmp = Path(tempfile.mkdtemp(prefix="lr", dir="/tmp"))
try:
    (HERE / "last_loop.c").write_text(T.LOOP_PROGRAM)
    binary = T.compile_loop_fixture(os.environ.get("CC", "cc"), base_tmp, AIRPLAY,
                                    sanitize=True)
    env = dict(os.environ)
    env.setdefault("ASAN_OPTIONS", "detect_leaks=1:abort_on_error=1")
    env.setdefault("UBSAN_OPTIONS", "halt_on_error=1:print_stacktrace=1")
    measured = {"biscuit", "radar_puffin"}
    variants = []
    for target in ("biscuit", "radar_puffin"):
        variants.append((target,
                         T.platform_targets.identity_bytes(target),
                         T.platform_targets.audio_profile_bytes(target)))
    variants.append(("lidar_s16_4096", LIDAR_IDENTITY, LIDAR_PROFILE))

    failures = 0
    for name, ident, profile in variants:
        profile_dir = base_tmp / "profile" / name
        profile_dir.mkdir(parents=True)
        (profile_dir / "target").write_bytes(ident)
        (profile_dir / "audio-profile").write_bytes(profile)
        base = base_tmp / "loop" / name
        base.mkdir(parents=True)
        run_env = dict(env,
                       LE_AUDIO_ENGINE_SENDSPIN_PROFILE_DIR=str(profile_dir),
                       LE_EXPECT_SENDSPIN_TIMING=(
                           "valid" if name in measured else "invalid"))
        cmd = f"{binary} {base} rtstart"
        print(f"\n=== target {name}: {cmd}", flush=True)
        proc = subprocess.run([str(binary), str(base), "rtstart"], timeout=180,
                              env=run_env, capture_output=True, text=True)
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        print(f"=== target {name}: exit {proc.returncode}", flush=True)
        if proc.returncode != 0:
            failures += 1
    print(f"\nvariants failed: {failures}/{len(variants)}")
    sys.exit(1 if failures else 0)
finally:
    shutil.rmtree(base_tmp, ignore_errors=True)
