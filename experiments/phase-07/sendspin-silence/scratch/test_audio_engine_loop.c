#define _GNU_SOURCE
#define main libreecho_audio_engine_main
#include "audio_engine.c"
#undef main

#include <stdarg.h>
#include <sys/wait.h>

/*
 * Task 4b-loop: outer-loop harness for run_engine().
 *
 * The REAL production run_engine()/main loop is executed in a forked child
 * against a fake TinyALSA PCM *and* mixer, private root FIFOs and a real
 * SOCK_SEQPACKET client driven from the parent.  No host /sys /dev /run /data
 * path is ever reached: open/open64/openat/connect are link-wrapped and any
 * denylisted path is refused and recorded.
 */

/* ------------------------------------------------------------------ */
/* Event log                                                          */
/* ------------------------------------------------------------------ */

#define EV_MAX 16384
struct ev { uint32_t tag, a, b, c; int32_t d; };
#define T_PCM_OPEN 1u
#define T_PCM_PREPARE 2u
#define T_PCM_WRITE 3u
#define T_PCM_CLOSE 4u
#define T_MIX_OPEN 5u
#define T_MIX_CLOSE 6u
#define T_MIX_ENUM 7u
#define T_MIX_SET 8u
#define T_AUDIT_DENY 9u
#define T_PCM_OPEN_FAIL 10u
#define T_PCM_WRITE_NEG 11u
/* a = flags, b = period_size, c = period_count: S32_LE opened */
#define T_PCM_WIDE_OPEN 12u
/* a = flags: S32_LE refused (hw_params), silently, as a real kernel does */
#define T_PCM_WIDE_REJECT 13u

struct engine_log {
    uint32_t magic;
    uint32_t count;
    uint32_t audit_denied;
    uint32_t rt_underruns;
    struct ev ev[EV_MAX];
};

#define LOG_MAGIC 0x4C4F4F50u

static struct ev g_ev[EV_MAX];
static int g_ev_n;
static int g_audit_denied;
static uint32_t g_rt_underruns;   /* real-time ring ran dry before a write */
static int g_slow_unmute_pending; /* SCEN_RTSTART: one hardware-like mixer stall */
static char g_root[700];
static int g_ev_fd = -1;
static int g_ctl_fd = -1;

static void logev(uint32_t tag, uint32_t a, uint32_t b, uint32_t c, int32_t d)
{
    if (g_ev_n < EV_MAX) {
        g_ev[g_ev_n].tag = tag;
        g_ev[g_ev_n].a = a;
        g_ev[g_ev_n].b = b;
        g_ev[g_ev_n].c = c;
        g_ev[g_ev_n].d = d;
        g_ev_n += 1;
    }
}

static void notify(char c)
{
    if (g_ev_fd >= 0) {
        ssize_t ignored = write(g_ev_fd, &c, 1);
        (void)ignored;
    }
}

/* ------------------------------------------------------------------ */
/* Path audit: deny any host hardware path except our private root    */
/* ------------------------------------------------------------------ */

static const char *const g_deny_prefix[] = {
    "/sys/", "/dev/", "/run/", "/data/", "/proc/", "/etc/"
};

static int path_denied(const char *path)
{
    unsigned int i;

    if (!path || path[0] != '/')
        return 0;
    if (g_root[0] != '\0' && strncmp(path, g_root, strlen(g_root)) == 0)
        return 0;
    for (i = 0; i < sizeof(g_deny_prefix) / sizeof(g_deny_prefix[0]); ++i)
        if (strncmp(path, g_deny_prefix[i], strlen(g_deny_prefix[i])) == 0)
            return 1;
    return 0;
}

/* The engine reads its image identity and speaker profile from fixed /etc
 * (and /proc/1/root/etc) paths at startup.  Those four exact paths are served
 * from the per-target sandbox profile directory the driver renders from the
 * Platform target table; without that directory they stay denied. */
static const char *g_profile_dir;
static const char *const g_profile_paths[][2] = {
    { "/etc/libreecho/target", "target" },
    { "/proc/1/root/etc/libreecho/target", "target" },
    { "/etc/libreecho/audio-profile", "audio-profile" },
    { "/proc/1/root/etc/libreecho/audio-profile", "audio-profile" },
};

static const char *sandbox_profile_path(const char *path, char *buf,
                                        size_t size)
{
    unsigned int i;

    if (!path || !g_profile_dir)
        return path;
    for (i = 0; i < sizeof(g_profile_paths) / sizeof(g_profile_paths[0]); ++i)
        if (strcmp(path, g_profile_paths[i][0]) == 0) {
            int n = snprintf(buf, size, "%s/%s", g_profile_dir,
                             g_profile_paths[i][1]);
            return n > 0 && (size_t)n < size ? buf : path;
        }
    return path;
}

static void record_denied(uint32_t kind, const char *path)
{
    uint32_t b = 0u, c = 0u;
    size_t n = path ? strlen(path) : 0u;

    if (n > 0u) memcpy(&b, path, n > 4u ? 4u : n);
    if (n > 4u) memcpy(&c, path + 4u, n > 8u ? 4u : n - 4u);
    g_audit_denied += 1;
    logev(T_AUDIT_DENY, kind, b, c, (int32_t)n);
}

extern int __real_open(const char *path, int flags, ...);
extern int __real_open64(const char *path, int flags, ...);
extern int __real_openat(int dirfd, const char *path, int flags, ...);
extern int __real_connect(int fd, const struct sockaddr *addr, socklen_t len);

int __wrap_open(const char *path, int flags, ...)
{
    char profile_buf[768];

    path = sandbox_profile_path(path, profile_buf, sizeof(profile_buf));
    if (path_denied(path)) {
        record_denied(1u, path);
        errno = EACCES;
        return -1;
    }
    if (flags & O_CREAT) {
        va_list ap;
        int mode;
        va_start(ap, flags);
        mode = va_arg(ap, int);
        va_end(ap);
        return __real_open(path, flags, mode);
    }
    return __real_open(path, flags);
}

int __wrap_open64(const char *path, int flags, ...)
{
    char profile_buf[768];

    path = sandbox_profile_path(path, profile_buf, sizeof(profile_buf));
    if (path_denied(path)) {
        record_denied(1u, path);
        errno = EACCES;
        return -1;
    }
    if (flags & O_CREAT) {
        va_list ap;
        int mode;
        va_start(ap, flags);
        mode = va_arg(ap, int);
        va_end(ap);
        return __real_open64(path, flags, mode);
    }
    return __real_open64(path, flags);
}

int __wrap_openat(int dirfd, const char *path, int flags, ...)
{
    char profile_buf[768];

    path = sandbox_profile_path(path, profile_buf, sizeof(profile_buf));
    if (path_denied(path)) {
        record_denied(1u, path);
        errno = EACCES;
        return -1;
    }
    if (flags & O_CREAT) {
        va_list ap;
        int mode;
        va_start(ap, flags);
        mode = va_arg(ap, int);
        va_end(ap);
        return __real_openat(dirfd, path, flags, mode);
    }
    return __real_openat(dirfd, path, flags);
}

int __wrap_connect(int fd, const struct sockaddr *addr, socklen_t len)
{
    if (addr && addr->sa_family == AF_UNIX) {
        const struct sockaddr_un *un = (const struct sockaddr_un *)addr;
        if (path_denied(un->sun_path)) {
            record_denied(2u, un->sun_path);
            errno = EACCES;
            return -1;
        }
    }
    return __real_connect(fd, addr, len);
}

/* ------------------------------------------------------------------ */
/* Fake TinyALSA PCM                                                  */
/* ------------------------------------------------------------------ */

struct pcm {
    unsigned int buffer_frames;
    int ready;
    int wide;       /* opened S32_LE: writes carry int32 (24-bit) frames */
    int rejected;   /* S32_LE refused at hw_params: never a usable stream */
    int rt_started;            /* LE_FAKE_PCM_REALTIME drain clock */
    int rt_any_write;          /* a write has started the drain */
    int rt_dry_checked;        /* underrun already evaluated for this write */
    struct timespec rt_start;
    uint64_t rt_written;
};

/* Scenario fault scripts (set in the child before run_engine). */
#define SCEN_PRIME 1
#define SCEN_FINISH 2
#define SCEN_LEGACY 3
#define SCEN_EPIPE 4
#define SCEN_RESTART 5
#define SCEN_MIXFAIL 6
#define SCEN_PREPFAIL 7
#define SCEN_STOP 8
#define SCEN_MEDIA 9
#define SCEN_PCMFAIL 10
/* Timing model unavailable after the PCM starts: the opened PCM reports a
 * zero-frame buffer, which is the realistic path by which
 * le_audio_timing_create() fails closed. */
#define SCEN_NOTIMING 11
#define SCEN_NOTIMING_LEGACY 12
/* Timing model present but the DAC timestamp query fails persistently: the
 * bounded ledger must fail the generation closed (cancel, not complete). */
#define SCEN_QUERYFAIL 13
/* 24-bit (S32_LE) output accepted by the fake kernel.  Every other scenario
 * runs with S32_LE refused, i.e. through the engine's S16 fallback. */
#define SCEN_WIDE_FINISH 14
#define SCEN_WIDE_EPIPE 15
/* Real-time ring (see fake_realtime()): a stop-and-wait producer -- the
 * companion's shape: one DATA, then wait for its CREDIT -- must be credited
 * at no less than the 48 kHz hardware rate. */
#define SCEN_THROUGHPUT 16
#define SCEN_IDLEWAKE 17
#define SCEN_RTSTART 18

static int g_scen;
static int g_fail_open;
static int g_fail_prepare;
static int g_no_timing_buffer;   /* opened PCM reports a 0-frame buffer */
static int g_hts_fail;           /* pcm_get_htimestamp() fails persistently */
static int g_wide_ok;            /* fake kernel accepts S32_LE playback */

/* Fault injection for one period: armed by the parent through the ctl pipe. */
static int g_arm_fail;
static int g_fail_state;         /* 0 idle, 1 partial done, 2 failed */
static unsigned int g_partial = 500u;
static int g_fail_errno = EPIPE;
static unsigned int g_write_calls;
static int16_t g_written[1 << 20];
static size_t g_written_frames;

static void poll_ctl(void)
{
    char cmd;
    ssize_t n;

    if (g_ctl_fd < 0 || g_arm_fail)
        return;
    n = read(g_ctl_fd, &cmd, 1);
    if (n == 1) {
        if (cmd == 'F') { g_arm_fail = 1; g_fail_state = 0; g_fail_errno = EPIPE; }
        else if (cmd == 'S') { g_arm_fail = 1; g_fail_state = 0; g_fail_errno = ESTRPIPE; }
    }
}

struct pcm *pcm_open(unsigned int card, unsigned int device, unsigned int flags,
                     const struct pcm_config *config)
{
    struct pcm *pcm;

    (void)card;
    (void)device;
    if (g_fail_open) {
        /* A failed open is still recorded so the harness can prove the loop
         * really attempted the PCM (and did not spin retrying it). */
        logev(T_PCM_OPEN_FAIL, flags, config->channels, config->rate, 0);
        notify('X');
        return NULL;
    }
    pcm = (struct pcm *)calloc(1, sizeof(*pcm));
    if (!pcm)
        return NULL;
    if (config->format == PCM_FORMAT_S32_LE) {
        if (!g_wide_ok) {
            /* hw_params refusal: a non-ready handle, no stream events. */
            pcm->rejected = 1;
            logev(T_PCM_WIDE_REJECT, flags, 0u, 0u, 0);
            return pcm;
        }
        pcm->wide = 1;
        logev(T_PCM_WIDE_OPEN, flags, config->period_size,
              config->period_count, 0);
    }
    /* A zero-frame buffer is the realistic fault by which
     * le_audio_timing_create() returns NULL (no observable DAC timeline). */
    pcm->buffer_frames = g_no_timing_buffer
                             ? 0u
                             : config->period_size * config->period_count;
    pcm->ready = 1;
    logev(T_PCM_OPEN, flags, config->channels, config->rate,
          (int32_t)(config->period_size | (config->period_count << 16)));
    notify('O');
    return pcm;
}

int pcm_is_ready(struct pcm *pcm)
{
    return pcm != NULL && pcm->ready;
}

const char *pcm_get_error(struct pcm *pcm)
{
    (void)pcm;
    return "fake-pcm";
}

void pcm_close(struct pcm *pcm)
{
    if (pcm && pcm->rejected) {
        free(pcm);          /* the refused S32_LE probe was never a stream */
        return;
    }
    logev(T_PCM_CLOSE, 0u, 0u, 0u, 0);
    notify('C');
    free(pcm);
}

int pcm_prepare(struct pcm *pcm)
{
    (void)pcm;
    logev(T_PCM_PREPARE, 0u, 0u, 0u, 0);
    return g_fail_prepare ? -1 : 0;
}

unsigned int pcm_get_buffer_size(const struct pcm *pcm)
{
    return pcm ? pcm->buffer_frames : 0u;
}

/*
 * Opt-in real-time drain (LE_FAKE_PCM_REALTIME): the ring drains at 48 kHz
 * from the first write and pcm_writei() blocks until the frames fit, as a
 * real blocking PCM does.  The deterministic scenarios keep the default
 * instant-drain model; the SDK throughput lane needs hardware pacing, since
 * an instantly-draining fake hides any per-period sink-service ceiling.
 */
static int fake_realtime(void)
{
    static int cached = -1;
    if (g_scen == SCEN_THROUGHPUT || g_scen == SCEN_RTSTART)
        return 1;
    if (cached < 0)
        cached = getenv("LE_FAKE_PCM_REALTIME") != NULL;
    return cached;
}

/*
 * LE_FAKE_PCM_PPM (|ppm| <= 1000) makes the fake DAC crystal run fast or
 * slow against CLOCK_MONOTONIC, as a real codec clock drifts from the system
 * clock: the hardware pointer advances at 48 kHz * (1 + ppm / 1e6).
 */
static double rt_rate(void)
{
    static double cached = 0.0;
    if (cached == 0.0) {
        const char *text = getenv("LE_FAKE_PCM_PPM");
        double ppm = text ? atof(text) : 0.0;
        if (ppm < -1000.0 || ppm > 1000.0)
            ppm = 0.0;
        cached = 48000.0 * (1.0 + ppm / 1e6);
    }
    return cached;
}

static unsigned int rt_queued(struct pcm *pcm, const struct timespec *now)
{
    int64_t elapsed_ns, drained;
    uint64_t written = pcm->rt_written;

    if (!pcm->rt_started)
        return 0u;
    elapsed_ns = (int64_t)(now->tv_sec - pcm->rt_start.tv_sec) * 1000000000LL +
                 (now->tv_nsec - pcm->rt_start.tv_nsec);
    drained = elapsed_ns > 0 ? (int64_t)((double)elapsed_ns * rt_rate() / 1e9) : 0;
    if ((uint64_t)drained >= written) {
        /* Underrun: the playhead stops at the tail; restart the drain clock
         * there so the next write is not credited with idle time. */
        pcm->rt_start = *now;
        pcm->rt_written = 0u;
        return 0u;
    }
    return (unsigned int)(written - (uint64_t)drained);
}

static void rt_block_until_room(struct pcm *pcm, unsigned int frames)
{
    for (;;) {
        struct timespec now, ts;
        unsigned int queued;

        if (clock_gettime(CLOCK_MONOTONIC, &now) != 0)
            return;
        if (!pcm->rt_started) {
            pcm->rt_started = 1;
            pcm->rt_start = now;
            pcm->rt_written = 0u;
        }
        queued = rt_queued(pcm, &now);
        if (queued == 0u && pcm->rt_dry_checked == 0 && pcm->rt_any_write) {
            /* The playhead reached the tail before this write: on hardware
             * an XRUN (EPIPE under PCM_NORESTART). */
            g_rt_underruns += 1u;
        }
        pcm->rt_dry_checked = 1;
        if (queued + frames <= pcm->buffer_frames)
            return;
        ts.tv_sec = 0;
        ts.tv_nsec = (long)((double)(queued + frames - pcm->buffer_frames) *
                            1e9 / rt_rate()) + 100000L;
        nanosleep(&ts, NULL);
    }
}

int pcm_get_htimestamp(struct pcm *pcm, unsigned int *avail,
                       struct timespec *timestamp)
{
    (void)pcm;
    if (!avail || !timestamp)
        return -1;
    if (g_hts_fail) {
        errno = EIO;             /* persistent query failure: no timestamp */
        return -1;
    }
    if (clock_gettime(CLOCK_MONOTONIC, timestamp) != 0)
        return -1;
    if (pcm && fake_realtime()) {
        *avail = pcm->buffer_frames - rt_queued(pcm, timestamp);
        return 0;
    }
    /* Deterministic fully-drained ring: nothing left in flight, so the
     * physical playhead equals the accepted-frame counter. */
    *avail = pcm ? pcm->buffer_frames : 0u;
    return 0;
}

/*
 * LE_FAKE_PCM_ONSET_LOG: append the true CLOCK_MONOTONIC time (ns) at which
 * each click leaves the fake DAC (the first loud frame after >= 200 ms of
 * quiet), for multi-player synchronization analysis. The frame's play time
 * follows from the drain model: drain epoch start + its index / rate.
 */
static void rt_log_onsets(struct pcm *pcm, const void *data, unsigned int frames)
{
    static FILE *log;
    static int opened;
    static uint64_t quiet = 48000u;
    const char *path;
    unsigned int i;

    if (!opened) {
        opened = 1;
        path = getenv("LE_FAKE_PCM_ONSET_LOG");
        log = path ? fopen(path, "a") : NULL;
    }
    if (!log)
        return;
    for (i = 0; i < frames; ++i) {
        int v = pcm->wide ? (int)(((const int32_t *)data)[i * OUTPUT_CHANNELS] / 65536)
                          : ((const int16_t *)data)[i * OUTPUT_CHANNELS];
        if (v > 1500 || v < -1500) {
            if (quiet >= 9600u) {
                /* LE_FAKE_PCM_EXTRA_LATENCY_US: output delay past the
                 * pointer that the engine was not calibrated for. */
                const char *extra = getenv("LE_FAKE_PCM_EXTRA_LATENCY_US");
                double at = (double)pcm->rt_start.tv_sec * 1e9 + (double)pcm->rt_start.tv_nsec +
                            (double)(pcm->rt_written + i) * 1e9 / rt_rate() +
                            (extra ? atof(extra) * 1e3 : 0.0);
                fprintf(log, "onset_ns=%.0f\n", at);
                fflush(log);
            }
            quiet = 0u;
        } else {
            quiet += 1u;
        }
    }
}

int pcm_writei(struct pcm *pcm, const void *data, unsigned int frame_count)
{
    const int16_t *samples = (const int16_t *)data;
    unsigned int accepted;
    unsigned int i;
    unsigned int half = frame_count / 2u;
    unsigned int nz_first = 0u, nz_second = 0u;
    unsigned int neg = 0u;
    int16_t first;

    (void)pcm;
    poll_ctl();
    g_write_calls += 1;

    if (g_arm_fail && g_fail_state == 0) {
        accepted = g_partial < frame_count ? g_partial : frame_count;
        g_fail_state = 1;
    } else if (g_arm_fail && g_fail_state == 1) {
        g_fail_state = 2;
        errno = g_fail_errno;
        return -1;
    } else {
        accepted = frame_count;
    }

    if (!samples)
        return -1;
    if (pcm && fake_realtime()) {
        pcm->rt_dry_checked = 0;
        rt_block_until_room(pcm, accepted);
        rt_log_onsets(pcm, data, accepted);
        pcm->rt_written += accepted;
        pcm->rt_any_write = 1;
    }
    /* Wide frames are 24-bit MSB-aligned in int32: the top 16 bits are the
     * same programme sample the S16 path would carry. */
#define FAKE_SAMPLE(k) (pcm && pcm->wide ? \
        (int16_t)(((const int32_t *)data)[(k)] / 65536) : samples[(k)])
    first = accepted > 0u ? FAKE_SAMPLE(0) : 0;
    for (i = 0; i < accepted; ++i) {
        int16_t v = FAKE_SAMPLE(i * OUTPUT_CHANNELS);
        if (v != 0) {
            if (i < half) nz_first += 1; else nz_second += 1;
        }
        if (v < 0) neg += 1;
    }
    /* Bounded capture buffer: an intentionally unbounded write sequence (the
     * regression this fixture must catch) must not overflow the harness's own
     * log buffer -- the write-count assertions are what bound the loop. */
    if (g_written_frames + accepted <=
        (sizeof(g_written) / sizeof(g_written[0])) / OUTPUT_CHANNELS) {
        for (i = 0; i < accepted * OUTPUT_CHANNELS; ++i)
            g_written[g_written_frames * OUTPUT_CHANNELS + i] = FAKE_SAMPLE(i);
    }
#undef FAKE_SAMPLE
    g_written_frames += accepted;
    logev(T_PCM_WRITE, frame_count, (uint32_t)(uint16_t)first,
          nz_first | (nz_second << 16), (int32_t)accepted);
    if (neg > 0u)
        logev(T_PCM_WRITE_NEG, neg, frame_count, 0u, 0);
    notify('W');
    return (int)accepted;
}

/* ------------------------------------------------------------------ */
/* Fake TinyALSA mixer                                                */
/* ------------------------------------------------------------------ */

enum {
    C_MUTE = 0, C_AMP, C_DACMUX, C_CHCFG, C_RIGHT, C_HPDAC, C_HPL, C_HPR,
    C_HPRIN1, C_HPGAIN, C_PCMVOL, C_COUNT
};

static const char *const ctl_names[C_COUNT] = {
    "MFP Gpio Mute", "Ext_Speaker_Amp_Switch", "Audio_DacMux_Setting",
    "Board Channel Config", "Right Channel Only", "HP DAC Playback Switch",
    "HPL Output Mixer L_DAC Switch", "HPR Output Mixer R_DAC Switch",
    "HPR Output Mixer IN1_R Switch", "HP Driver Gain Volume",
    "PCM Playback Volume"
};

static int g_mixer_open_fail;
static int g_enum_off_fail;      /* make "MFP Gpio Mute"="Off" fail */

static int ctl_kind(int idx)
{
    if (idx == C_HPDAC || idx == C_HPGAIN || idx == C_PCMVOL)
        return 2;
    return 1;
}

struct mixer { int unused; };
struct mixer_ctl { int unused; };

struct mixer *mixer_open(unsigned int card)
{
    (void)card;
    if (g_mixer_open_fail)
        return NULL;
    logev(T_MIX_OPEN, 0u, 0u, 0u, 0);
    return (struct mixer *)malloc(sizeof(struct mixer));
}

void mixer_close(struct mixer *mixer)
{
    logev(T_MIX_CLOSE, 0u, 0u, 0u, 0);
    free(mixer);
}

struct mixer_ctl *mixer_get_ctl_by_name(struct mixer *mixer, const char *name)
{
    int i;

    (void)mixer;
    for (i = 0; i < C_COUNT; ++i)
        if (strcmp(name, ctl_names[i]) == 0)
            return (struct mixer_ctl *)(intptr_t)(i + 1);
    return NULL;
}

unsigned int mixer_ctl_get_num_values(struct mixer_ctl *ctl)
{
    int idx = (int)(intptr_t)ctl - 1;
    return (unsigned int)ctl_kind(idx);
}

int mixer_ctl_get_value(struct mixer_ctl *ctl, unsigned int index)
{
    int idx = (int)(intptr_t)ctl - 1;
    (void)index;
    if (idx == C_PCMVOL)
        return 127;
    return 0;
}

/* SCEN_RTSTART: on the Radar, codec verify + unmute after the first period
 * costs ~20-60 ms of mixer ioctls while that period already drains. */
static void slow_unmute_stall(void)
{
    if (g_slow_unmute_pending && g_write_calls > 0u) {
        struct timespec stall = { 0, 25L * 1000000L };

        g_slow_unmute_pending = 0;
        nanosleep(&stall, NULL);
    }
}

int mixer_ctl_set_value(struct mixer_ctl *ctl, unsigned int index, int value)
{
    int idx = (int)(intptr_t)ctl - 1;
    slow_unmute_stall();
    logev(T_MIX_SET, (uint32_t)idx, index, (uint32_t)value, 0);
    return 0;
}

int mixer_ctl_set_enum_by_string(struct mixer_ctl *ctl, const char *value)
{
    int idx = (int)(intptr_t)ctl - 1;
    slow_unmute_stall();
    uint32_t code = 9u;

    if (strcmp(value, "On") == 0) code = 1u;
    else if (strcmp(value, "Off") == 0) code = 0u;
    else if (strcmp(value, "Stereo") == 0) code = 2u;
    logev(T_MIX_ENUM, (uint32_t)idx, code, 0u, 0);
    if (g_enum_off_fail && idx == C_MUTE && code == 0u)
        return -1;
    return 0;
}

/* ------------------------------------------------------------------ */
/* Child                                                              */
/* ------------------------------------------------------------------ */

static void dump_log(const char *root, int rc)
{
    char path[600];
    struct engine_log *out = (struct engine_log *)calloc(1, sizeof(*out));
    int fd;

    if (!out)
        return;
    out->magic = LOG_MAGIC;
    out->count = (uint32_t)g_ev_n;
    out->audit_denied = (uint32_t)g_audit_denied;
    out->rt_underruns = g_rt_underruns;
    memcpy(out->ev, g_ev, sizeof(struct ev) * (size_t)g_ev_n);
    (void)snprintf(path, sizeof(path), "%s/engine.log", root);
    fd = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0640);
    if (fd >= 0) {
        ssize_t ignored = write(fd, out, sizeof(*out));
        (void)ignored;
        close(fd);
    }
    free(out);
    (void)rc;
}

static void child_main(const char *root, int scen, int ev_w, int ctl_r)
{
    struct sigaction action;

    g_scen = scen;
    g_ev_n = 0;
    g_audit_denied = 0;
    g_ev_fd = ev_w;
    g_ctl_fd = ctl_r;
    (void)snprintf(g_root, sizeof(g_root), "%s", root);
    if (ctl_r >= 0) {
        int fl = fcntl(ctl_r, F_GETFL, 0);
        if (fl >= 0)
            (void)fcntl(ctl_r, F_SETFL, fl | O_NONBLOCK);
    }
    signal(SIGPIPE, SIG_IGN);
    memset(&action, 0, sizeof(action));
    action.sa_handler = on_signal;
    sigemptyset(&action.sa_mask);
    (void)sigaction(SIGTERM, &action, NULL);
    (void)sigaction(SIGINT, &action, NULL);

    g_fail_open = 0;
    g_fail_prepare = 0;
    g_mixer_open_fail = 0;
    g_enum_off_fail = 0;
    g_arm_fail = 0;
    g_fail_state = 0;
    g_write_calls = 0;
    g_written_frames = 0u;
    g_no_timing_buffer = 0;
    g_hts_fail = 0;
    g_wide_ok = (scen == SCEN_WIDE_FINISH || scen == SCEN_WIDE_EPIPE ||
                 scen == SCEN_RTSTART);
    g_rt_underruns = 0u;
    g_slow_unmute_pending = (scen == SCEN_RTSTART);
    if (scen == SCEN_MIXFAIL)
        g_mixer_open_fail = 1;
    if (scen == SCEN_PREPFAIL)
        g_fail_prepare = 1;
    if (scen == SCEN_PCMFAIL)
        g_fail_open = 1;
    if (scen == SCEN_NOTIMING || scen == SCEN_NOTIMING_LEGACY)
        g_no_timing_buffer = 1;
    if (scen == SCEN_QUERYFAIL)
        g_hts_fail = 1;

    (void)run_engine(root, 0u, 23u);
    dump_log(root, 0);
    _exit(0);
}

/* ------------------------------------------------------------------ */
/* Parent helpers                                                     */
/* ------------------------------------------------------------------ */

static int g_fail;

static void check(int cond, const char *label)
{
    if (!cond) {
        fprintf(stderr, "engine-loop FAIL: %s\n", label);
        g_fail += 1;
    }
}

static int spawn(const char *root, int scen, pid_t *out_pid, int *out_ev,
                 int *out_ctl)
{
    int ev[2], ctl[2];
    pid_t pid;

    if (pipe(ev) != 0 || pipe(ctl) != 0)
        return -1;
    pid = fork();
    if (pid < 0)
        return -1;
    if (pid == 0) {
        close(ev[0]);
        close(ctl[1]);
        child_main(root, scen, ev[1], ctl[0]);
        _exit(0);
    }
    close(ev[1]);
    close(ctl[0]);
    *out_pid = pid;
    *out_ev = ev[0];
    *out_ctl = ctl[1];
    return 0;
}

static int finish_child(pid_t pid, int ev_r, int ctl_w)
{
    int status = 0, i;

    close(ev_r);
    if (ctl_w >= 0)
        close(ctl_w);
    kill(pid, SIGTERM);
    for (i = 0; i < 300; ++i) {
        pid_t r = waitpid(pid, &status, WNOHANG);
        if (r == pid)
            return status;
        {
            struct timespec ts = {0, 10000000L};
            nanosleep(&ts, NULL);
        }
    }
    kill(pid, SIGKILL);
    (void)waitpid(pid, &status, 0);
    return status;
}

/* Poll the child event pipe for byte `want`.  Returns 0 on seen, -1 timeout
 * or EOF.  The budget is a wall-clock deadline, not only accumulated poll
 * timeouts: a child that keeps emitting events (for example the unbounded
 * pacing this harness must be able to catch) must still time out. */
static int wait_event(int fd, char want, int timeout_ms)
{
    struct timespec start;

    if (clock_gettime(CLOCK_MONOTONIC, &start) != 0)
        return -1;
    for (;;) {
        struct pollfd p;
        char buf[256];
        ssize_t n;
        ssize_t i;
        struct timespec now;
        long elapsed;
        int r;

        p.fd = fd;
        p.events = POLLIN;
        p.revents = 0;
        r = poll(&p, 1, 100);
        if (r < 0) {
            if (errno == EINTR)
                continue;
            return -1;
        }
        if (r > 0) {
            n = read(fd, buf, sizeof(buf));
            if (n <= 0)
                return -1;
            for (i = 0; i < n; ++i)
                if (buf[i] == want)
                    return 0;
        }
        if (clock_gettime(CLOCK_MONOTONIC, &now) != 0)
            return -1;
        elapsed = (now.tv_sec - start.tv_sec) * 1000L +
                  (now.tv_nsec - start.tv_nsec) / 1000000L;
        if (elapsed >= (long)timeout_ms)
            return -1;
    }
}

static int connect_client(const char *path, int timeout_ms)
{
    int waited = 0;

    /* Never truncate silently: an AF_UNIX sun_path holds at most
     * sizeof(sun_path) - 1 bytes plus NUL, and a path that does not fit would
     * connect nowhere and report an opaque "connect failed" instead of the
     * real over-length cause. */
    if (strlen(path) >= sizeof(((struct sockaddr_un *)0)->sun_path)) {
        check(0, "loop: socket path exceeds sun_path; shorten the scratch base");
        return -1;
    }
    while (waited < timeout_ms) {
        int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
        struct sockaddr_un addr;
        struct timeval tv = {5, 0};

        if (fd < 0)
            return -1;
        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        (void)snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", path);
        if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) == 0) {
            (void)setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
            return fd;
        }
        close(fd);
        {
            struct timespec ts = {0, 1000000L};
            nanosleep(&ts, NULL);
        }
        waited += 1;
    }
    return -1;
}

static int send_datagram(int fd, uint8_t type, const uint8_t *payload,
                         uint32_t plen)
{
    uint8_t buf[LE_AUDIO_SINK_HEADER_BYTES + LE_AUDIO_SINK_MAX_PAYLOAD_BYTES];
    size_t total = LE_AUDIO_SINK_HEADER_BYTES + (size_t)plen;

    if (plen > LE_AUDIO_SINK_MAX_PAYLOAD_BYTES)
        return -1;
    le_audio_sink_encode_header(buf, type, plen);
    if (plen)
        memcpy(buf + LE_AUDIO_SINK_HEADER_BYTES, payload, plen);
    return send(fd, buf, total, 0) == (ssize_t)total ? 0 : -1;
}

static int recv_datagram(int fd, uint8_t *type, uint8_t *payload,
                         uint32_t *plen)
{
    uint8_t buf[LE_AUDIO_SINK_MAX_DATAGRAM_BYTES];
    struct le_audio_sink_header h;
    ssize_t n = recv(fd, buf, sizeof(buf), 0);

    if (n < (ssize_t)LE_AUDIO_SINK_HEADER_BYTES)
        return -1;
    if (le_audio_sink_decode_header(buf, (size_t)n, &h) != LE_AUDIO_SINK_OK)
        return -1;
    *type = h.type;
    if (plen)
        *plen = h.length;
    if (payload && h.length)
        memcpy(payload, buf + LE_AUDIO_SINK_HEADER_BYTES, h.length);
    return 0;
}

static uint32_t g_last_error;

static int expect_type(int fd, uint8_t want, uint8_t *payload, uint32_t *plen)
{
    int i;

    for (i = 0; i < 128; ++i) {
        uint8_t t;
        uint8_t tmp[64];
        uint32_t tl = 0;

        if (recv_datagram(fd, &t, tmp, &tl) != 0)
            return -1;
        if (t == LE_AUDIO_SINK_TYPE_ERROR) {
            if (tl >= 4u)
                g_last_error = le_audio_sink_get_u32(tmp + 0);
            continue;
        }
        if (t == want) {
            if (payload && tl)
                memcpy(payload, tmp, tl);
            if (plen)
                *plen = tl;
            return 0;
        }
    }
    return -1;
}

/* Wait for an ERROR reply; returns the status or -1 on timeout. */
static int expect_error(int fd)
{
    int i;

    g_last_error = 0xffffffffu;
    for (i = 0; i < 128; ++i) {
        uint8_t t;
        uint8_t tmp[64];
        uint32_t tl = 0;

        if (recv_datagram(fd, &t, tmp, &tl) != 0)
            return -1;
        if (t == LE_AUDIO_SINK_TYPE_ERROR) {
            if (tl >= 4u)
                g_last_error = le_audio_sink_get_u32(tmp + 0);
            return (int)g_last_error;
        }
    }
    return -1;
}

static int cl_open(int fd, uint32_t gen, uint32_t *epoch, uint32_t *status)
{
    uint8_t p[LE_AUDIO_SINK_OPEN_PAYLOAD_BYTES];
    uint8_t r[64];
    uint32_t rl = 0;
    int rc;

    memset(p, 0, sizeof(p));
    le_audio_sink_put_u32(p + 0, LE_AUDIO_SINK_SOURCE_SENDPIN);
    le_audio_sink_put_u32(p + 4, gen);
    le_audio_sink_put_u32(p + 8, LE_AUDIO_SINK_OUTPUT_RATE);
    le_audio_sink_put_u16(p + 12, LE_AUDIO_SINK_OUTPUT_CHANNELS);
    le_audio_sink_put_u16(p + 14, LE_AUDIO_SINK_FORMAT_S16_LE);
    if (send_datagram(fd, LE_AUDIO_SINK_TYPE_OPEN, p, sizeof(p)) != 0)
        return -1;
    rc = expect_type(fd, LE_AUDIO_SINK_TYPE_OPEN_ACK, r, &rl);
    if (rc != 0)
        return rc;
    *status = le_audio_sink_get_u32(r + 0);
    *epoch = le_audio_sink_get_u32(r + 4);
    return 0;
}

static int cl_data(int fd, uint32_t epoch, uint32_t gen, uint32_t seq,
                   uint64_t first, uint32_t frames, int16_t value, int wait_credit)
{
    uint8_t p[LE_AUDIO_SINK_DATA_PREFIX_BYTES + LE_AUDIO_SINK_MAX_DATA_FRAMES * 4u];
    uint8_t r[64];
    uint32_t rl = 0;
    uint32_t i;

    memset(p, 0, LE_AUDIO_SINK_DATA_PREFIX_BYTES);
    le_audio_sink_put_u32(p + 0, epoch);
    le_audio_sink_put_u32(p + 4, gen);
    le_audio_sink_put_u32(p + 8, seq);
    le_audio_sink_put_u64(p + 16, first);
    le_audio_sink_put_u32(p + 24, frames);
    for (i = 0; i < frames; ++i) {
        le_audio_sink_put_u16(p + LE_AUDIO_SINK_DATA_PREFIX_BYTES + i * 4u,
                              (uint16_t)value);
        le_audio_sink_put_u16(p + LE_AUDIO_SINK_DATA_PREFIX_BYTES + i * 4u + 2u,
                              (uint16_t)value);
    }
    if (send_datagram(fd, LE_AUDIO_SINK_TYPE_DATA, p,
                      LE_AUDIO_SINK_DATA_PREFIX_BYTES + frames * 4u) != 0)
        return -1;
    if (!wait_credit)
        return 0;
    return expect_type(fd, LE_AUDIO_SINK_TYPE_CREDIT, r, &rl);
}

static int cl_finish(int fd, uint32_t epoch, uint32_t gen, uint64_t total,
                     uint32_t seq)
{
    uint8_t p[LE_AUDIO_SINK_FINISH_PAYLOAD_BYTES];

    memset(p, 0, sizeof(p));
    le_audio_sink_put_u32(p + 0, epoch);
    le_audio_sink_put_u32(p + 4, gen);
    le_audio_sink_put_u64(p + 8, total);
    le_audio_sink_put_u32(p + 16, seq);
    return send_datagram(fd, LE_AUDIO_SINK_TYPE_FINISH, p, sizeof(p));
}

static int cl_progress(int fd, uint32_t epoch, uint32_t gen, uint8_t *out,
                       uint32_t *outlen)
{
    uint8_t p[LE_AUDIO_SINK_PROGRESS_REQ_PAYLOAD_BYTES];

    memset(p, 0, sizeof(p));
    le_audio_sink_put_u32(p + 0, epoch);
    le_audio_sink_put_u32(p + 4, gen);
    if (send_datagram(fd, LE_AUDIO_SINK_TYPE_PROGRESS_REQ, p, sizeof(p)) != 0)
        return -1;
    return expect_type(fd, LE_AUDIO_SINK_TYPE_PROGRESS, out, outlen);
}

/* Write a full hardware period to a legacy FIFO (non-blocking). */
static int aec_receiver_open(const char *root)
{
    char path[700];
    struct sockaddr_un addr;
    int fd;

    (void)snprintf(path, sizeof(path), "%s/aec-reference.sock", root);
    if (strlen(path) >= sizeof(addr.sun_path))
        return -1;
    fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0)
        return -1;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    memcpy(addr.sun_path, path, strlen(path) + 1u);
    (void)unlink(path);
    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) != 0) {
        close(fd);
        return -1;
    }
    return fd;
}

/* Look for one published AEC reference packet carrying at least `bits`
 * (0 = any).  Proves the real le_aec_reference_publish path ran in the loop. */
static int aec_receiver_check(int fd, unsigned int bits)
{
    int i;

    for (i = 0; i < 16; ++i) {
        struct le_aec_reference_packet packet;
        struct pollfd p;
        ssize_t n;

        p.fd = fd;
        p.events = POLLIN;
        p.revents = 0;
        if (poll(&p, 1, 1000) <= 0)
            return -1;
        n = recv(fd, &packet, sizeof(packet), 0);
        if (n < (ssize_t)sizeof(packet.header))
            return -1;
        if (packet.header.magic != LE_AEC_REFERENCE_MAGIC ||
            packet.header.frames != PERIOD_SIZE ||
            packet.header.channels != 1u)
            return -1;
        if ((packet.header.activity_mask & bits) == bits)
            return 0;
    }
    return -1;
}

static int write_fifo_period(const char *root, const char *name,
                             const int16_t *pattern, size_t frames)
{
    char path[600];
    int fd;
    int i;
    size_t total = frames * LE_AUDIO_SINK_OUTPUT_CHANNELS;
    uint8_t buf[2048u * 4u];

    (void)snprintf(path, sizeof(path), "%s/%s", root, name);
    for (i = 0; i < 2000; ++i) {
        fd = open(path, O_WRONLY | O_NONBLOCK | O_CLOEXEC);
        if (fd >= 0)
            break;
        {
            struct timespec ts = {0, 1000000L};
            nanosleep(&ts, NULL);
        }
    }
    if (fd < 0)
        return -1;
    for (i = 0; i < (int)total; ++i)
        ((int16_t *)buf)[i] = pattern[i];
    if ((size_t)frames * 4u > sizeof(buf))
        return -1;
    if (write(fd, buf, total * sizeof(int16_t)) < 0) {
        close(fd);
        return -1;
    }
    close(fd);
    return 0;
}

/* ------------------------------------------------------------------ */
/* Log loading + assertions                                           */
/* ------------------------------------------------------------------ */

static struct engine_log g_log;

static int load_log(const char *root)
{
    char path[600];
    int fd;
    ssize_t n;

    memset(&g_log, 0, sizeof(g_log));
    (void)snprintf(path, sizeof(path), "%s/engine.log", root);
    fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0)
        return -1;
    n = read(fd, &g_log, sizeof(g_log));
    close(fd);
    if (n < (ssize_t)offsetof(struct engine_log, ev) ||
        g_log.magic != LOG_MAGIC)
        return -1;
    if (g_log.count > EV_MAX)
        g_log.count = EV_MAX;
    return 0;
}

static int count_tag(uint32_t tag)
{
    uint32_t i;
    int c = 0;

    for (i = 0; i < g_log.count; ++i)
        if (g_log.ev[i].tag == tag)
            c += 1;
    return c;
}

static int index_tag(uint32_t tag, int occurrence)
{
    uint32_t i;
    int c = 0;

    for (i = 0; i < g_log.count; ++i) {
        if (g_log.ev[i].tag == tag) {
            if (c == occurrence)
                return (int)i;
            c += 1;
        }
    }
    return -1;
}

static int count_mix(uint32_t name, uint32_t code)
{
    uint32_t i;
    int c = 0;

    for (i = 0; i < g_log.count; ++i)
        if (g_log.ev[i].tag == T_MIX_ENUM && g_log.ev[i].a == name &&
            g_log.ev[i].b == code)
            c += 1;
    return c;
}

static int last_mix_index(void)
{
	int i;
	for (i = (int)g_log.count - 1; i >= 0; --i) {
		if (g_log.ev[i].tag == T_MIX_ENUM || g_log.ev[i].tag == T_MIX_SET)
			return i;
	}
	return -1;
}

/* Count intercepted path denials by kind (1 = open, 2 = connect). */
static int count_audit_kind(uint32_t kind)
{
	uint32_t i;
	int c = 0;

	for (i = 0; i < g_log.count; ++i)
		if (g_log.ev[i].tag == T_AUDIT_DENY && g_log.ev[i].a == kind)
			c += 1;
	return c;
}

/* Total negative samples across every period written to the fake PCM. */
static unsigned int count_negative_samples(void)
{
	uint32_t i;
	unsigned int total = 0u;

	for (i = 0; i < g_log.count; ++i)
		if (g_log.ev[i].tag == T_PCM_WRITE_NEG)
			total += g_log.ev[i].a;
	return total;
}

/* check() with a "<scenario>: <message>" label built at run time. */
static void checkf(const char *tag, const char *message, int cond)
{
	char label[192];

	if (cond)
		return;
	(void)snprintf(label, sizeof(label), "%s: %s", tag, message);
	check(0, label);
}

/* ------------------------------------------------------------------ */
/* Scenarios                                                          */
/* ------------------------------------------------------------------ */

static const char *const g_scen_names[] = {
    "", "prime", "finish", "legacy", "epipe", "restart", "mixfail",
    "prepfail", "stop", "media", "pcmfail", "notiming", "notiminglegacy",
    "queryfail", "widefinish", "wideepipe", "throughput", "idlewake", "rtstart"
};

static void make_root(const char *base, const char *name, char *out,
                      size_t outlen)
{
    char vol[700];
    int fd;

    (void)snprintf(out, outlen, "%s/%s", base, name);
    (void)mkdir(out, 0770);
    /* A concrete logical master keeps the renderer/DSP path audible so the
     * loop's content checks are meaningful. */
    (void)snprintf(vol, sizeof(vol), "%s/master.volume", out);
    fd = open(vol, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0640);
    if (fd >= 0) {
        ssize_t ignored = write(fd, "80\n", 3);
        (void)ignored;
        close(fd);
    }
}

/* Scenario 1: socket OPEN with every legacy FIFO idle -> priming reaches the
 * PCM and produces bounded paced silence with no FIFO period ever ready. */
static void scen_prime(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, fd, i;
    uint32_t epoch = 0, status = 0;
    uint8_t prog[64];
    uint32_t proglen = 0;
    int writes;

    make_root(base, g_scen_names[SCEN_PRIME], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    if (spawn(root, SCEN_PRIME, &pid, &ev, &ctl) != 0) {
        check(0, "prime: spawn failed");
        return;
    }
    fd = connect_client(sock, 3000);
    check(fd >= 0, "prime: real SOCK_SEQPACKET connect failed");
    if (fd >= 0) {
        check(cl_open(fd, 1u, &epoch, &status) == 0 && status == 0u &&
              epoch != 0u,
              "prime: OPEN was not served while every FIFO was idle");
        check(wait_event(ev, 'O', 5000) == 0,
              "prime: idle-socket generation never reached the PCM");
        check(wait_event(ev, 'C', 8000) == 0,
              "prime: bounded priming never closed the PCM");
        check(cl_progress(fd, epoch, 1u, prog, &proglen) == 0,
              "prime: PROGRESS was not served");
        close(fd);
    }
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "prime: engine log missing");
    check(g_log.audit_denied == 0u,
          "prime: the loop reached an external /sys /dev /run /data path");
    writes = count_tag(T_PCM_WRITE);
    check(count_tag(T_PCM_OPEN) == 1, "prime: PCM was not opened exactly once");
    check(count_tag(T_PCM_CLOSE) == 1, "prime: PCM was not closed");
    check(count_tag(T_PCM_PREPARE) == 1, "prime: PCM was not prepared once");
    check(writes >= 2 && writes <= (int)SENDPIN_PRIME_LIMIT + 4,
          "prime: priming silence was not bounded");
    for (i = 0; i < (int)g_log.count; ++i) {
        if (g_log.ev[i].tag == T_PCM_WRITE)
            check((g_log.ev[i].c & 0xffffu) == 0u &&
                  (g_log.ev[i].c >> 16) == 0u,
                  "prime: priming write was not silence");
    }
    /* geometry + flags actually used by the loop */
    {
        int o = index_tag(T_PCM_OPEN, 0);
        check(o >= 0 &&
              g_log.ev[o].a == (PCM_OUT | PCM_MONOTONIC | PCM_NORESTART),
              "prime: PCM opened without PCM_OUT|PCM_MONOTONIC|PCM_NORESTART");
        check(o >= 0 && g_log.ev[o].b == OUTPUT_CHANNELS && g_log.ev[o].c == DEFAULT_RATE,
              "prime: PCM geometry channels/rate wrong");
        check(o >= 0 && (g_log.ev[o].d & 0xffff) == (int)PERIOD_SIZE &&
              ((g_log.ev[o].d >> 16) & 0xffff) == (int)PERIOD_COUNT,
              "prime: PCM period_size/period_count wrong");
    }
    /* armed muted, amp on while muted, then unmuted, then disabled on teardown */
    check(count_mix(C_MUTE, 1u) >= 1, "prime: mute was never asserted before amp");
    check(count_mix(C_AMP, 1u) >= 1, "prime: amp was never enabled");
    check(count_mix(C_MUTE, 0u) >= 1, "prime: output was never unmuted");
    {
        int l = last_mix_index();
        check(l >= 0 && g_log.ev[l].tag == T_MIX_ENUM &&
              g_log.ev[l].a == C_AMP && g_log.ev[l].b == 0u,
              "prime: teardown did not end with amp off");
        if (l >= 1)
            check(g_log.ev[l - 1].tag == T_MIX_ENUM &&
                  g_log.ev[l - 1].a == C_MUTE && g_log.ev[l - 1].b == 1u,
                  "prime: teardown did not mute before removing amp power");
    }
}

/* Scenario 2: DATA short exact tail + FINISH -> physical completion, PCM
 * closes, no further DATA. */
static void scen_finish(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, fd;
    uint32_t epoch = 0, status = 0;
    uint8_t prog[64];
    uint32_t proglen = 0;

    make_root(base, g_scen_names[SCEN_FINISH], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    if (spawn(root, SCEN_FINISH, &pid, &ev, &ctl) != 0) {
        check(0, "finish: spawn failed");
        return;
    }
    fd = connect_client(sock, 3000);
    check(fd >= 0, "finish: connect failed");
    if (fd >= 0) {
        check(cl_open(fd, 1u, &epoch, &status) == 0 && status == 0u,
              "finish: OPEN failed");
        check(cl_data(fd, epoch, 1u, 0u, 0u, 512u, 2000, 1) == 0,
              "finish: short DATA period was not credited");
        check(cl_finish(fd, epoch, 1u, 512u, 0u) == 0,
              "finish: FINISH send failed");
        check(wait_event(ev, 'C', 8000) == 0,
              "finish: completed generation never closed the PCM");
        check(cl_progress(fd, epoch, 1u, prog, &proglen) == 0,
              "finish: PROGRESS not served after completion");
        close(fd);
    }
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "finish: engine log missing");
    check(g_log.audit_denied == 0u,
          "finish: the loop reached an external /sys /dev /run /data path");
    check(count_tag(T_PCM_OPEN) == 1 && count_tag(T_PCM_CLOSE) == 1,
          "finish: PCM did not open/close once");
    check(count_tag(T_PCM_WIDE_REJECT) == 1 && count_tag(T_PCM_WIDE_OPEN) == 0,
          "finish: S32_LE refusal did not fall back to S16 exactly once");
    {
        int r = index_tag(T_PCM_WIDE_REJECT, 0);
        check(r >= 0 &&
              g_log.ev[r].a == (PCM_OUT | PCM_MONOTONIC | PCM_NORESTART),
              "finish: 24-bit attempt opened without MONOTONIC|NORESTART");
    }
    check(count_tag(T_PCM_WRITE) >= 1 && count_tag(T_PCM_WRITE) <= 4,
          "finish: unexpected number of periods after FINISH");
    if (proglen == LE_AUDIO_SINK_PROGRESS_PAYLOAD_BYTES) {
        uint64_t submitted = le_audio_sink_get_u64(prog + 16);
        uint64_t played = le_audio_sink_get_u64(prog + 32);
        check(submitted == 512u,
              "finish: physical completion did not stop at the exact source tail");
        check(played == 512u,
              "finish: playhead did not reach the exact FINISH tail");
        /* The speaker chain's measured output latency calibrates timing:
         * a measured chain publishes a VALID finish, an unmeasured one
         * fails closed.  The driver names the expectation per target. */
        {
            const char *expect = getenv("LE_EXPECT_SENDSPIN_TIMING");
            uint32_t flags = le_audio_sink_get_u32(prog + 12);
            uint64_t finish_us = le_audio_sink_get_u64(prog + 24);

            check(expect != NULL, "finish: driver set no timing expectation");
            if (expect && strcmp(expect, "valid") == 0)
                check((flags & LE_AUDIO_SINK_PROGRESS_TIMING_VALID) != 0u &&
                      finish_us != 0u,
                      "finish: measured chain did not publish VALID timing");
            else if (expect)
                check((flags & LE_AUDIO_SINK_PROGRESS_TIMING_VALID) == 0u &&
                      finish_us == 0u,
                      "finish: unmeasured chain published a finish estimate");
        }
    }
}

/* Scenario 3: legacy-only FIFO accumulation (two half-period writes per
 * period) preserves both halves with no zero padding; AEC reference and LED
 * (announcement) paths stay on the real loop. */
static void scen_legacy(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, aec;
    int16_t pat_a[PERIOD_SIZE * LE_AUDIO_SINK_OUTPUT_CHANNELS];
    int16_t pat_b[PERIOD_SIZE * LE_AUDIO_SINK_OUTPUT_CHANNELS];
    int16_t pat_c[PERIOD_SIZE * LE_AUDIO_SINK_OUTPUT_CHANNELS];
    int16_t pat_d[PERIOD_SIZE * LE_AUDIO_SINK_OUTPUT_CHANNELS];
    unsigned int i;
    int n_first, n_second;

    make_root(base, g_scen_names[SCEN_LEGACY], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    aec = aec_receiver_open(root);
    for (i = 0; i < PERIOD_SIZE * LE_AUDIO_SINK_OUTPUT_CHANNELS; ++i) {
        pat_a[i] = (int16_t)3000;
        pat_b[i] = (int16_t)-3000;
        pat_c[i] = (int16_t)1500;
        pat_d[i] = (int16_t)-1500;
    }
    if (spawn(root, SCEN_LEGACY, &pid, &ev, &ctl) != 0) {
        check(0, "legacy: spawn failed");
        return;
    }
    /* Announcement periods are queued first so the higher-priority bus stays
     * live for every rendered period; the real LED transport call is then
     * made and denied, and the visualizer path is not fed raw media. */
    check(write_fifo_period(root, "announcement.pcm", pat_a, PERIOD_SIZE) == 0 &&
          write_fifo_period(root, "announcement.pcm", pat_a, PERIOD_SIZE) == 0 &&
          write_fifo_period(root, "announcement.pcm", pat_a, PERIOD_SIZE) == 0,
          "legacy: announcement period writes failed");
    /* Two full media periods delivered as four half-period writes. */
    check(write_fifo_period(root, "media.pcm", pat_a, PERIOD_SIZE / 2u) == 0 &&
          write_fifo_period(root, "media.pcm", pat_b, PERIOD_SIZE / 2u) == 0 &&
          write_fifo_period(root, "media.pcm", pat_c, PERIOD_SIZE / 2u) == 0 &&
          write_fifo_period(root, "media.pcm", pat_d, PERIOD_SIZE / 2u) == 0,
          "legacy: half-period FIFO writes failed");
    check(wait_event(ev, 'W', 8000) == 0, "legacy: no legacy period reached the PCM");
    check(aec >= 0 && aec_receiver_check(aec, PLAYBACK_BUS_ANNOUNCEMENT) == 0,
          "legacy: the AEC reference / priority activity mask path was not exercised");
    if (aec >= 0)
        close(aec);
    check(wait_event(ev, 'C', 8000) == 0, "legacy: PCM was not closed");
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "legacy: engine log missing");
    check(count_tag(T_PCM_WRITE) >= 1, "legacy: no PCM period written");
    {
        int w = index_tag(T_PCM_WRITE, 0);
        n_first = w >= 0 ? (int)(g_log.ev[w].c & 0xffffu) : -1;
        n_second = w >= 0 ? (int)(g_log.ev[w].c >> 16) : -1;
        check(n_first > 0 && n_second > 0,
              "legacy: a half-period was zero-padded into the rendered period");
    }
    check(g_log.audit_denied >= 1u,
          "legacy: the engine LED /run path was not intercepted and denied");
    check(count_mix(C_CHCFG, 2u) >= 1,
          "legacy: stereo board channel config was not selected");
}

/* Scenario 4/4b: an injected XRUN mid-period tears the loop down, keeps the old
 * generation inactive across real polling, and a higher OPEN recovers with no
 * replay of the predecessor's frames.  The fault is always delivered as
 * pcm_writei()==-1 with errno set (never a -errno return); the ESTRPIPE errno
 * is exercised in addition to EPIPE. */
static void scen_xrun(const char *base, int scen, char ctl_cmd, const char *tag)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, fd, i;
    uint32_t epoch1 = 0, status = 0, epoch2 = 0;
    int write2 = -1;

    make_root(base, tag, root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    if (spawn(root, scen, &pid, &ev, &ctl) != 0) {
        checkf(tag, "spawn failed", 0);
        return;
    }
    fd = connect_client(sock, 3000);
    checkf(tag, "connect failed", fd >= 0);
    if (fd >= 0) {
        checkf(tag, "OPEN gen1 failed",
               cl_open(fd, 1u, &epoch1, &status) == 0 && status == 0u);
        /* Arm the injected failure before any write, then queue real source. */
        checkf(tag, "fail arm failed", write(ctl, &ctl_cmd, 1) == 1);
        checkf(tag, "gen1 DATA send failed",
               cl_data(fd, epoch1, 1u, 0u, 0u, PERIOD_SIZE, 1000, 0) == 0);
        checkf(tag, "injected failure did not tear down the PCM",
               wait_event(ev, 'C', 6000) == 0);
        /* Old generation must stay inactive across the loop's own polling. */
        checkf(tag, "the fenced generation was re-adopted at the next poll",
               cl_data(fd, epoch1, 1u, 1u, PERIOD_SIZE, 64u, 1000, 0) == 0 &&
               expect_error(fd) == LE_AUDIO_SINK_ERR_STALE_GENERATION);
        /* A fresh strictly higher OPEN recovers. */
        checkf(tag, "higher OPEN did not recover",
               cl_open(fd, 2u, &epoch2, &status) == 0 && status == 0u);
        checkf(tag, "epoch changed within the same engine", epoch2 == epoch1);
        checkf(tag, "recovery DATA was not credited",
               cl_data(fd, epoch2, 2u, 0u, 0u, PERIOD_SIZE, 20000, 1) == 0);
        checkf(tag, "recovery generation never reached the PCM",
               wait_event(ev, 'W', 6000) == 0);
        {
            uint8_t p2[64];
            uint32_t p2len = 0;
            if (cl_progress(fd, epoch2, 2u, p2, &p2len) == 0 &&
                p2len == LE_AUDIO_SINK_PROGRESS_PAYLOAD_BYTES) {
                const unsigned long long sub = (unsigned long long)
                    le_audio_sink_get_u64(p2 + 16);
                if (sub != PERIOD_SIZE)
                    fprintf(stderr, "%s: recovery generation submitted %llu frames, want %u\n",
                            tag, sub, (unsigned)PERIOD_SIZE);
                checkf(tag, "recovery replayed predecessor frames into the new generation",
                       sub == PERIOD_SIZE);
            }
        }
        close(fd);
    }
    (void)finish_child(pid, ev, ctl);
    checkf(tag, "engine log missing", load_log(root) == 0);
    checkf(tag, "the PCM was not reopened for the recovery generation",
           count_tag(T_PCM_OPEN) >= 2);
    for (i = 0; i < (int)g_log.count; ++i)
        if (g_log.ev[i].tag == T_PCM_WRITE &&
            (g_log.ev[i].c & 0xffffu) != 0u && write2 < 0)
            write2 = i;
    checkf(tag, "the recovery generation never carried its own payload",
           write2 >= 0);
}

static void scen_epipe(const char *base)
{
    scen_xrun(base, SCEN_EPIPE, 'F', "epipe");
}

static void scen_estripe(const char *base)
{
    scen_xrun(base, SCEN_EPIPE, 'S', "estripe");
}

/* Scenario 5: engine restart -> a new epoch; the old epoch is rejected and a
 * fresh generation is admitted. */
static void scen_restart(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, fd;
    uint32_t epoch1 = 0, epoch2 = 0, status = 0;

    make_root(base, g_scen_names[SCEN_RESTART], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    if (spawn(root, SCEN_RESTART, &pid, &ev, &ctl) != 0) {
        check(0, "restart: spawn failed");
        return;
    }
    fd = connect_client(sock, 3000);
    check(fd >= 0, "restart: first connect failed");
    if (fd >= 0) {
        check(cl_open(fd, 5u, &epoch1, &status) == 0 && status == 0u &&
              epoch1 != 0u,
              "restart: first engine OPEN failed");
        close(fd);
    }
    (void)finish_child(pid, ev, ctl);

    /* Second engine instance on the same private root. */
    if (spawn(root, SCEN_RESTART, &pid, &ev, &ctl) != 0) {
        check(0, "restart: second spawn failed");
        return;
    }
    fd = connect_client(sock, 3000);
    check(fd >= 0, "restart: second connect failed");
    if (fd >= 0) {
        check(cl_data(fd, epoch1, 5u, 0u, 0u, 64u, 500, 0) == 0 &&
              expect_error(fd) == LE_AUDIO_SINK_ERR_STALE_EPOCH,
              "restart: a stale-epoch DATA reached the new engine");
        check(cl_open(fd, 1u, &epoch2, &status) == 0 && status == 0u &&
              epoch2 != 0u,
              "restart: fresh generation rejected after restart");
        check(epoch2 != epoch1,
              "restart: restarted engine reused the previous epoch");
        check(cl_data(fd, epoch2, 1u, 0u, 0u, 64u, 700, 1) == 0,
              "restart: fresh DATA was not credited");
        close(fd);
    }
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "restart: engine log missing");
}

/* Scenario 6: mixer-open failure -> no PCM is ever opened and the loop keeps
 * running. */
static void scen_mixfail(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, fd, i;
    uint32_t epoch = 0, status = 0;

    make_root(base, g_scen_names[SCEN_MIXFAIL], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    if (spawn(root, SCEN_MIXFAIL, &pid, &ev, &ctl) != 0) {
        check(0, "mixfail: spawn failed");
        return;
    }
    fd = connect_client(sock, 3000);
    check(fd >= 0, "mixfail: connect failed");
    if (fd >= 0) {
        check(cl_open(fd, 1u, &epoch, &status) == 0 && status == 0u,
              "mixfail: OPEN failed");
        /* Give the loop several serviced polls, then stop. */
        for (i = 0; i < 3; ++i) {
            uint8_t p[64];
            uint32_t pl = 0;
            (void)cl_progress(fd, epoch, 1u, p, &pl);
        }
        close(fd);
    }
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "mixfail: engine log missing");
    check(count_tag(T_PCM_OPEN) == 0,
          "mixfail: PCM was opened even though the mixer was unavailable");
}

/* Scenario 7: PCM-prepare failure after a successful open -> teardown mutes
 * then removes amplifier power. */
static void scen_prepfail(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, fd, i;
    uint32_t epoch = 0, status = 0;
    int saw_open = 0;
    int lastl = -1;

    make_root(base, g_scen_names[SCEN_PREPFAIL], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    if (spawn(root, SCEN_PREPFAIL, &pid, &ev, &ctl) != 0) {
        check(0, "prepfail: spawn failed");
        return;
    }
    fd = connect_client(sock, 3000);
    check(fd >= 0, "prepfail: connect failed");
    if (fd >= 0) {
        check(cl_open(fd, 1u, &epoch, &status) == 0 && status == 0u,
              "prepfail: OPEN failed");
        check(wait_event(ev, 'O', 5000) == 0, "prepfail: PCM not opened");
        for (i = 0; i < 2; ++i) {
            uint8_t p[64];
            uint32_t pl = 0;
            (void)cl_progress(fd, epoch, 1u, p, &pl);
        }
        close(fd);
    }
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "prepfail: engine log missing");
    check(count_tag(T_PCM_PREPARE) >= 1 && count_tag(T_PCM_CLOSE) >= 1,
          "prepfail: a failed prepare did not close the opened PCM");
    for (i = 0; i < (int)g_log.count; ++i)
        if (g_log.ev[i].tag == T_PCM_OPEN)
            saw_open = 1;
    check(saw_open, "prepfail: PCM was not opened");
    lastl = last_mix_index();
    check(lastl >= 1 && g_log.ev[lastl].tag == T_MIX_ENUM &&
          g_log.ev[lastl].a == C_AMP && g_log.ev[lastl].b == 0u &&
          g_log.ev[lastl - 1].a == C_MUTE && g_log.ev[lastl - 1].b == 1u,
          "prepfail: teardown did not mute before removing amplifier power");
}

/* Scenario 7: SIGTERM during an active stream -> the stop path mutes before
 * dropping amplifier power and closes the PCM. */
static void scen_stop(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, fd;
    uint32_t epoch = 0, status = 0, proglen = 0;
    uint8_t prog[64];
    uint64_t submitted = 0;
    int lastl;

    make_root(base, g_scen_names[SCEN_STOP], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    if (spawn(root, SCEN_STOP, &pid, &ev, &ctl) != 0) {
        check(0, "stop: spawn failed");
        return;
    }
    fd = connect_client(sock, 3000);
    check(fd >= 0, "stop: connect failed");
    if (fd >= 0) {
        check(cl_open(fd, 1u, &epoch, &status) == 0 && status == 0u,
              "stop: OPEN failed");
        check(cl_data(fd, epoch, 1u, 0u, 0u, PERIOD_SIZE, 4000, 1) == 0,
              "stop: DATA was not credited");
        check(wait_event(ev, 'W', 6000) == 0,
              "stop: the active stream never wrote a period");
        check(cl_progress(fd, epoch, 1u, prog, &proglen) == 0,
              "stop: PROGRESS not served during the active stream");
        if (proglen == LE_AUDIO_SINK_PROGRESS_PAYLOAD_BYTES)
            submitted = le_audio_sink_get_u64(prog + 16);
        close(fd);
    }
    check(submitted > 0u, "stop: active stream did not advance the source cursor");
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "stop: engine log missing");
    check(count_tag(T_PCM_CLOSE) >= 1, "stop: PCM was not closed on stop");
    lastl = last_mix_index();
    check(lastl >= 1 && g_log.ev[lastl].tag == T_MIX_ENUM &&
          g_log.ev[lastl].a == C_AMP && g_log.ev[lastl].b == 0u &&
          g_log.ev[lastl - 1].a == C_MUTE && g_log.ev[lastl - 1].b == 1u,
          "stop: stop path did not mute before removing amplifier power");
}

/* Scenario 8: media-only playback with no priority bus.  With the announcement
 * bus silent the loop really enters the music visualizer on the rendered
 * (negative) programme, so under UBSan the analyzer's old signed shift would
 * abort right here.  The LED transport call the visualizer makes is the only
 * external path touched, which proves the visualizer ran. */
static void scen_media(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, i;
    int16_t pattern[PERIOD_SIZE * LE_AUDIO_SINK_OUTPUT_CHANNELS];
    int writes;

    make_root(base, g_scen_names[SCEN_MEDIA], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    /* A 500 Hz bipolar tone: the rendered period carries real negative
     * samples into the visualizer (a constant offset could be high-passed
     * away by the speaker DSP, dodging the negative shift). */
    for (i = 0; i < (int)(PERIOD_SIZE * LE_AUDIO_SINK_OUTPUT_CHANNELS); ++i) {
        unsigned int frame =
            (unsigned int)i / LE_AUDIO_SINK_OUTPUT_CHANNELS;
        double phase = 2.0 * 3.14159265358979323846 * 500.0 *
            (double)frame / 48000.0;

        pattern[i] = (int16_t)lround(-12000.0 * sin(phase));
    }
    if (spawn(root, SCEN_MEDIA, &pid, &ev, &ctl) != 0) {
        check(0, "media: spawn failed");
        return;
    }
    check(write_fifo_period(root, "media.pcm", pattern, PERIOD_SIZE) == 0 &&
          write_fifo_period(root, "media.pcm", pattern, PERIOD_SIZE) == 0 &&
          write_fifo_period(root, "media.pcm", pattern, PERIOD_SIZE) == 0 &&
          write_fifo_period(root, "media.pcm", pattern, PERIOD_SIZE) == 0,
          "media: media.pcm period writes failed");
    check(wait_event(ev, 'W', 8000) == 0,
          "media: no media period reached the PCM");
    check(wait_event(ev, 'C', 8000) == 0,
          "media: PCM was not closed after the bounded media stream");
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "media: engine log missing");
    /* The visualizer is the only component that talks to the LED socket on
     * this media-only scenario, and the LED path is the only external path
     * reached (as a connect denial). */
    check(count_audit_kind(2u) >= 1,
          "media: the music visualizer LED frame path was never exercised");
    check(count_audit_kind(1u) == 0,
          "media: an unexpected external open path was reached");
    check(count_negative_samples() > 0u,
          "media: no negative PCM reached the rendered/visualizer buffer");
    writes = count_tag(T_PCM_WRITE);
    check(writes >= 1, "media: no PCM period written");
    check(count_tag(T_PCM_OPEN) == 1 && count_tag(T_PCM_CLOSE) == 1,
          "media: PCM did not open/close once");
    check(count_mix(C_CHCFG, 2u) >= 1,
          "media: stereo board channel config was not selected");
}

/* Scenario 9: the PCM cannot be opened at all.  The loop must attempt the
 * open, never credit it as a usable stream, tear the amplifier down in the
 * mute-before-amp-off order, and not spin retrying the failed open. */
static void scen_pcmfail(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, fd, i, lastl;
    uint32_t epoch = 0, status = 0;
    int attempts;

    make_root(base, g_scen_names[SCEN_PCMFAIL], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    if (spawn(root, SCEN_PCMFAIL, &pid, &ev, &ctl) != 0) {
        check(0, "pcmfail: spawn failed");
        return;
    }
    fd = connect_client(sock, 3000);
    check(fd >= 0, "pcmfail: connect failed");
    if (fd >= 0) {
        check(cl_open(fd, 1u, &epoch, &status) == 0 && status == 0u,
              "pcmfail: OPEN failed");
        check(wait_event(ev, 'X', 6000) == 0,
              "pcmfail: the loop never attempted the PCM open");
        /* Several serviced polls, then stop. */
        for (i = 0; i < 3; ++i) {
            uint8_t p[64];
            uint32_t pl = 0;
            (void)cl_progress(fd, epoch, 1u, p, &pl);
        }
        close(fd);
    }
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "pcmfail: engine log missing");
    check(count_tag(T_PCM_OPEN) == 0,
          "pcmfail: a failed pcm_open was credited as a usable stream");
    attempts = count_tag(T_PCM_OPEN_FAIL);
    check(attempts >= 1, "pcmfail: the PCM open was never attempted");
    check(attempts <= 8,
          "pcmfail: the engine spun retrying a failed PCM open");
    check(count_tag(T_PCM_WRITE) == 0,
          "pcmfail: a period was written through an unopened PCM");
    /* Arm set mute + amp off; the failure teardown must leave the same safe
     * order (mute before amplifier power is removed). */
    lastl = last_mix_index();
    check(lastl >= 1 && g_log.ev[lastl].tag == T_MIX_ENUM &&
          g_log.ev[lastl].a == C_AMP && g_log.ev[lastl].b == 0u &&
          g_log.ev[lastl - 1].a == C_MUTE && g_log.ev[lastl - 1].b == 1u,
          "pcmfail: teardown did not mute before removing amplifier power");
    check(count_mix(C_MUTE, 1u) >= 2 && count_mix(C_AMP, 0u) >= 2,
          "pcmfail: the output was not armed and re-disabled on the failure path");
}

/* Scenario 10: the timing model is unavailable after the PCM starts.  The
 * opened PCM reports a zero-frame buffer, so le_audio_timing_create() returns
 * NULL and the engine keeps running without a DAC timeline.  A FINISHed
 * generation can then never be observed as physically complete, so it must be
 * failed closed: the exact generation is cancelled with an explicit timing
 * error and the PCM is retired to the legacy path instead of pacing generated
 * silence forever.  No completion/playhead may be fabricated, the cancelled
 * generation must stay rejected (a successor, not a replay, is required), and
 * a fresh generation must still be admitted for recovery. */
static void scen_notiming(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, fd, l;
    uint32_t epoch = 0, status = 0, epoch2 = 0;
    int writes;

    make_root(base, g_scen_names[SCEN_NOTIMING], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    if (spawn(root, SCEN_NOTIMING, &pid, &ev, &ctl) != 0) {
        check(0, "notiming: spawn failed");
        return;
    }
    fd = connect_client(sock, 3000);
    check(fd >= 0, "notiming: connect failed");
    if (fd >= 0) {
        uint8_t pr[LE_AUDIO_SINK_PROGRESS_REQ_PAYLOAD_BYTES];

        check(cl_open(fd, 1u, &epoch, &status) == 0 && status == 0u,
              "notiming: OPEN was not served");
        check(cl_data(fd, epoch, 1u, 0u, 0u, 512u, 1000, 1) == 0,
              "notiming: source DATA was not credited");
        /* A live (unfinished) generation must still drive PCM periods with no
         * timing model: priming must not be rejected outright. */
        check(wait_event(ev, 'W', 8000) == 0,
              "notiming: a live generation without a timing model was never paced");
        check(cl_finish(fd, epoch, 1u, 512u, 0u) == 0,
              "notiming: FINISH send failed");
        /* Without timing the tail cannot be observed: the loop must fail the
         * generation closed and retire the PCM within a bounded window. */
        check(wait_event(ev, 'C', 8000) == 0,
              "notiming: a FINISHed generation without a timing model paced the PCM forever");
        /* A cancelled generation must not report live progress: no fabricated
         * completion or playhead. */
        memset(pr, 0, sizeof(pr));
        le_audio_sink_put_u32(pr + 0, epoch);
        le_audio_sink_put_u32(pr + 4, 1u);
        check(send_datagram(fd, LE_AUDIO_SINK_TYPE_PROGRESS_REQ, pr,
                            sizeof(pr)) == 0 &&
              expect_error(fd) == LE_AUDIO_SINK_ERR_STALE_GENERATION,
              "notiming: the failed generation still reported live progress");
        /* The cancelled generation must stay rejected; recovery needs a
         * fresh, strictly higher generation. */
        check(cl_data(fd, epoch, 1u, 1u, 512u, 64u, 1000, 0) == 0 &&
              expect_error(fd) == LE_AUDIO_SINK_ERR_STALE_GENERATION,
              "notiming: a cancelled generation was revived by late DATA");
        check(cl_open(fd, 2u, &epoch2, &status) == 0 && status == 0u &&
              epoch2 == epoch,
              "notiming: a fresh generation was not admitted for recovery");
        close(fd);
    }
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "notiming: engine log missing");
    check(g_log.audit_denied == 0u,
          "notiming: the loop reached an external /sys /dev /run /data path");
    writes = count_tag(T_PCM_WRITE);
    check(writes >= 1,
          "notiming: no PCM period was written before the fail-closed retire");
    check(writes <= 2 * (int)SENDPIN_PRIME_LIMIT + 16,
          "notiming: a timing-less FINISH was paced without limit");
    check(count_tag(T_PCM_OPEN) >= 1 && count_tag(T_PCM_OPEN) <= 2,
          "notiming: the engine reopened the PCM in a spin after the fail-closed retire");
    check(count_tag(T_PCM_CLOSE) >= 1, "notiming: PCM was not retired");
    l = last_mix_index();
    check(l >= 1 && g_log.ev[l].tag == T_MIX_ENUM &&
          g_log.ev[l].a == C_AMP && g_log.ev[l].b == 0u &&
          g_log.ev[l - 1].a == C_MUTE && g_log.ev[l - 1].b == 1u,
          "notiming: teardown did not mute before removing amplifier power");
}

/* Scenario 11: a legacy FIFO session is already streaming when a Sendspin OPEN
 * arrives and FINISHes, and the running PCM has no timing model.  The
 * generation must still be failed closed, but legacy playback must continue:
 * the loop keeps mixing/ writing the legacy bus instead of starving or
 * spinning on the unobservable Sendspin tail. */
static void scen_notiming_legacy(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, fd, i, l;
    uint32_t epoch = 0, status = 0;
    int16_t pat[PERIOD_SIZE * LE_AUDIO_SINK_OUTPUT_CHANNELS];
    int nz_writes = 0;
    uint32_t idx;

    make_root(base, g_scen_names[SCEN_NOTIMING_LEGACY], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    /* A 500 Hz bipolar tone keeps real (nonzero) samples in the rendered
     * period, so the legacy path is distinguishable from generated silence. */
    for (i = 0; i < (int)(PERIOD_SIZE * LE_AUDIO_SINK_OUTPUT_CHANNELS); ++i) {
        unsigned int frame = (unsigned int)i / LE_AUDIO_SINK_OUTPUT_CHANNELS;
        double phase = 2.0 * 3.14159265358979323846 * 500.0 *
            (double)frame / 48000.0;

        pat[i] = (int16_t)lround(-12000.0 * sin(phase));
    }
    if (spawn(root, SCEN_NOTIMING_LEGACY, &pid, &ev, &ctl) != 0) {
        check(0, "notiminglegacy: spawn failed");
        return;
    }
    check(write_fifo_period(root, "media.pcm", pat, PERIOD_SIZE) == 0 &&
          write_fifo_period(root, "media.pcm", pat, PERIOD_SIZE) == 0 &&
          write_fifo_period(root, "media.pcm", pat, PERIOD_SIZE) == 0 &&
          write_fifo_period(root, "media.pcm", pat, PERIOD_SIZE) == 0 &&
          write_fifo_period(root, "media.pcm", pat, PERIOD_SIZE) == 0 &&
          write_fifo_period(root, "media.pcm", pat, PERIOD_SIZE) == 0,
          "notiminglegacy: legacy FIFO writes failed");
    check(wait_event(ev, 'W', 8000) == 0,
          "notiminglegacy: the legacy stream never reached the PCM");
    /* OPEN while the legacy PCM (no timing model) is already streaming. */
    fd = connect_client(sock, 3000);
    check(fd >= 0, "notiminglegacy: connect failed");
    if (fd >= 0) {
        uint8_t pr[LE_AUDIO_SINK_PROGRESS_REQ_PAYLOAD_BYTES];

        check(cl_open(fd, 1u, &epoch, &status) == 0 && status == 0u,
              "notiminglegacy: OPEN while legacy playing failed");
        check(cl_data(fd, epoch, 1u, 0u, 0u, 512u, 1000, 1) == 0,
              "notiminglegacy: source DATA was not credited");
        check(cl_finish(fd, epoch, 1u, 512u, 0u) == 0,
              "notiminglegacy: FINISH send failed");
        check(wait_event(ev, 'C', 10000) == 0,
              "notiminglegacy: the timing-less Sendspin tail kept the PCM paced forever");
        memset(pr, 0, sizeof(pr));
        le_audio_sink_put_u32(pr + 0, epoch);
        le_audio_sink_put_u32(pr + 4, 1u);
        check(send_datagram(fd, LE_AUDIO_SINK_TYPE_PROGRESS_REQ, pr,
                            sizeof(pr)) == 0 &&
              expect_error(fd) == LE_AUDIO_SINK_ERR_STALE_GENERATION,
              "notiminglegacy: the failed Sendspin generation still reported live progress");
        close(fd);
    }
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "notiminglegacy: engine log missing");
    /* The media visualizer's LED `connect` is an intended denial on this
     * path; no external open() may be reached. */
    check(count_audit_kind(1u) == 0,
          "notiminglegacy: an unexpected external open path was reached");
    for (idx = 0u; idx < g_log.count; ++idx)
        if (g_log.ev[idx].tag == T_PCM_WRITE &&
            ((g_log.ev[idx].c & 0xffffu) != 0u ||
             (g_log.ev[idx].c >> 16) != 0u))
            nz_writes += 1;
    check(nz_writes >= 1,
          "notiminglegacy: legacy audio stopped reaching the PCM at the Sendspin OPEN");
    check(count_tag(T_PCM_WRITE) <= 2 * (int)SENDPIN_PRIME_LIMIT + 32,
          "notiminglegacy: the loop paced an unbounded number of periods");
    check(count_tag(T_PCM_CLOSE) >= 1, "notiminglegacy: PCM was not retired");
    l = last_mix_index();
    check(l >= 1 && g_log.ev[l].tag == T_MIX_ENUM &&
          g_log.ev[l].a == C_AMP && g_log.ev[l].b == 0u &&
          g_log.ev[l - 1].a == C_MUTE && g_log.ev[l - 1].b == 1u,
          "notiminglegacy: teardown did not mute before removing amplifier power");
}

/* Scenario 12 (control, reviewer F2): the timing model IS present but
 * pcm_get_htimestamp() fails persistently.  This path is already bounded by
 * the fixed timing ledger: the generated padding fills LE_AUDIO_LEDGER_CAPACITY,
 * the accounting refuses, and the generation is CANCELLED -- never a
 * fabricated completion and never a wall-clock fallback.  The exact source
 * tail is not replayed.  This guards the timing-present path while the
 * no-timing path is fixed. */
static void scen_queryfail(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, fd, l;
    uint32_t epoch = 0, status = 0;
    int writes;

    make_root(base, g_scen_names[SCEN_QUERYFAIL], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    if (spawn(root, SCEN_QUERYFAIL, &pid, &ev, &ctl) != 0) {
        check(0, "queryfail: spawn failed");
        return;
    }
    fd = connect_client(sock, 3000);
    check(fd >= 0, "queryfail: connect failed");
    if (fd >= 0) {
        uint8_t pr[LE_AUDIO_SINK_PROGRESS_REQ_PAYLOAD_BYTES];

        check(cl_open(fd, 1u, &epoch, &status) == 0 && status == 0u,
              "queryfail: OPEN failed");
        check(cl_data(fd, epoch, 1u, 0u, 0u, 512u, 1000, 1) == 0,
              "queryfail: source DATA was not credited");
        check(cl_finish(fd, epoch, 1u, 512u, 0u) == 0,
              "queryfail: FINISH send failed");
        check(wait_event(ev, 'C', 8000) == 0,
              "queryfail: a persistent timestamp-query failure paced the PCM without bound");
        memset(pr, 0, sizeof(pr));
        le_audio_sink_put_u32(pr + 0, epoch);
        le_audio_sink_put_u32(pr + 4, 1u);
        check(send_datagram(fd, LE_AUDIO_SINK_TYPE_PROGRESS_REQ, pr,
                            sizeof(pr)) == 0 &&
              expect_error(fd) == LE_AUDIO_SINK_ERR_STALE_GENERATION,
              "queryfail: a query-failed generation was reported completed/valid");
        close(fd);
    }
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "queryfail: engine log missing");
    check(g_log.audit_denied == 0u,
          "queryfail: the loop reached an external /sys /dev /run /data path");
    writes = count_tag(T_PCM_WRITE);
    check(writes >= 1, "queryfail: no PCM period was written");
    check(writes <= (int)LE_AUDIO_LEDGER_CAPACITY + 8,
          "queryfail: ledger-full containment did not bound the loop");
    check(count_tag(T_PCM_CLOSE) >= 1, "queryfail: PCM was not retired");
    l = last_mix_index();
    check(l >= 1 && g_log.ev[l].tag == T_MIX_ENUM &&
          g_log.ev[l].a == C_AMP && g_log.ev[l].b == 0u &&
          g_log.ev[l - 1].a == C_MUTE && g_log.ev[l - 1].b == 1u,
          "queryfail: teardown did not mute before removing amplifier power");
}

/* Interceptor self-test: the deny policy must reject a host hardware path. */
static void audit_selftest(const char *base)
{
    char root[600];
    int fd;

    make_root(base, "auditselftest", root, sizeof(root));
    (void)snprintf(g_root, sizeof(g_root), "%s", root);
    g_audit_denied = 0;
    fd = open("/dev/null", O_RDONLY);
    check(fd < 0, "audit: /dev/null was not denied");
    if (fd >= 0)
        close(fd);
    check(g_audit_denied == 1, "audit: deny interception was not exercised");
    g_root[0] = '\0';
}

/* Scenario 14: 24-bit output.  The fake kernel accepts S32_LE, so the
 * Sendspin generation renders through the wide path: the PCM is opened
 * 3 x 1024 with MONOTONIC|NORESTART, the timing ledger sizes itself from the
 * 3072-frame ring, programme content reaches the DAC as 24-bit words and the
 * exact FINISH tail completes. */
static void scen_wide_finish(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, fd, i, nonzero = 0;
    uint32_t epoch = 0, status = 0;
    uint8_t prog[64];
    uint32_t proglen = 0;

    make_root(base, g_scen_names[SCEN_WIDE_FINISH], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    if (spawn(root, SCEN_WIDE_FINISH, &pid, &ev, &ctl) != 0) {
        check(0, "widefinish: spawn failed");
        return;
    }
    fd = connect_client(sock, 3000);
    check(fd >= 0, "widefinish: connect failed");
    if (fd >= 0) {
        check(cl_open(fd, 1u, &epoch, &status) == 0 && status == 0u,
              "widefinish: OPEN failed");
        check(cl_data(fd, epoch, 1u, 0u, 0u, 512u, 6000, 1) == 0,
              "widefinish: short DATA period was not credited");
        check(cl_finish(fd, epoch, 1u, 512u, 0u) == 0,
              "widefinish: FINISH send failed");
        check(wait_event(ev, 'C', 8000) == 0,
              "widefinish: completed generation never closed the PCM");
        check(cl_progress(fd, epoch, 1u, prog, &proglen) == 0,
              "widefinish: PROGRESS not served after completion");
        close(fd);
    }
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "widefinish: engine log missing");
    check(g_log.audit_denied == 0u,
          "widefinish: the loop reached an external /sys /dev /run /data path");
    check(count_tag(T_PCM_WIDE_REJECT) == 0 && count_tag(T_PCM_WIDE_OPEN) == 1,
          "widefinish: the PCM was not opened S32_LE exactly once");
    {
        int w = index_tag(T_PCM_WIDE_OPEN, 0);
        check(w >= 0 &&
              g_log.ev[w].a == (PCM_OUT | PCM_MONOTONIC | PCM_NORESTART),
              "widefinish: S32_LE opened without MONOTONIC|NORESTART");
        check(w >= 0 && g_log.ev[w].b == 1024u && g_log.ev[w].c == 3u,
              "widefinish: S32_LE geometry is not 3 x 1024");
    }
    check(count_tag(T_PCM_OPEN) == 1 && count_tag(T_PCM_CLOSE) == 1,
          "widefinish: PCM did not open/close once");
    /* One period may be silence: the first source frame waits for a whole
     * period or FINISH (start gate), and DATA arrives before FINISH. */
    check(count_tag(T_PCM_WRITE) >= 1 && count_tag(T_PCM_WRITE) <= 3,
          "widefinish: unexpected number of periods after FINISH");
    for (i = 0; i < (int)g_log.count; ++i)
        if (g_log.ev[i].tag == T_PCM_WRITE && (g_log.ev[i].c & 0xffffu) != 0u)
            nonzero = 1;
    check(nonzero, "widefinish: Sendspin programme never reached the 24-bit DAC words");
    check(proglen == LE_AUDIO_SINK_PROGRESS_PAYLOAD_BYTES,
          "widefinish: PROGRESS payload missing");
    if (proglen == LE_AUDIO_SINK_PROGRESS_PAYLOAD_BYTES) {
        check(le_audio_sink_get_u64(prog + 16) == 512u,
              "widefinish: completion did not stop at the exact source tail");
        check(le_audio_sink_get_u64(prog + 32) == 512u,
              "widefinish: playhead did not reach the exact FINISH tail");
    }
}

/* Scenario 15: an XRUN after a partial 24-bit write accounts only the
 * accepted prefix, fences the generation, and a higher OPEN recovers on a
 * reopened S32_LE PCM with no replay. */
static double mono_seconds(void)
{
    struct timespec t;
    (void)clock_gettime(CLOCK_MONOTONIC, &t);
    return (double)t.tv_sec + (double)t.tv_nsec / 1e9;
}

/* One stop-and-wait DATA as the companion sends it: a CAPACITY refusal
 * accepts nothing and the same sequence is offered again once there is room;
 * CREDIT is the only acceptance. */
static int cl_data_until_credit(int fd, uint32_t epoch, uint32_t seq,
                                uint64_t first, uint32_t frames)
{
    int tries;

    for (tries = 0; tries < 5000; ++tries) {
        uint8_t t;
        uint8_t tmp[64];
        uint32_t tl = 0;

        if (cl_data(fd, epoch, 1u, seq, first, frames, 1000, 0) != 0 ||
            recv_datagram(fd, &t, tmp, &tl) != 0)
            return -1;
        if (t == LE_AUDIO_SINK_TYPE_CREDIT)
            return 0;
        if (t != LE_AUDIO_SINK_TYPE_ERROR || tl < 4u ||
            (g_last_error = le_audio_sink_get_u32(tmp + 0)) !=
                LE_AUDIO_SINK_ERR_CAPACITY)
            return -1;
        {
            struct timespec pause = {0, 1000000L};
            nanosleep(&pause, NULL);
        }
    }
    return -1;
}

static void scen_throughput(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, fd;
    uint32_t epoch = 0, status = 0, seq = 0;
    uint64_t first = 0;
    const uint32_t chunk = 512u;     /* a typical SDK write, < one period */
    double start = 0.0, elapsed = 0.0;

    make_root(base, g_scen_names[SCEN_THROUGHPUT], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    if (spawn(root, SCEN_THROUGHPUT, &pid, &ev, &ctl) != 0) {
        check(0, "throughput: spawn failed");
        return;
    }
    fd = connect_client(sock, 3000);
    check(fd >= 0, "throughput: connect failed");
    if (fd >= 0) {
        int ok = 1;

        check(cl_open(fd, 1u, &epoch, &status) == 0 && status == 0u,
              "throughput: OPEN failed");
        /* Fill the startup ring and queue first; then measure steady state. */
        while (ok && first < 4u * PERIOD_SIZE) {
            ok = cl_data_until_credit(fd, epoch, seq++, first, chunk) == 0;
            first += chunk;
        }
        start = mono_seconds();
        while (ok && (elapsed = mono_seconds() - start) < 1.5) {
            ok = cl_data_until_credit(fd, epoch, seq++, first, chunk) == 0;
            first += chunk;
        }
        if (!ok)
            fprintf(stderr, "throughput: DATA seq %u (first %llu) failed, last error %u\n",
                    (unsigned)(seq - 1u), (unsigned long long)(first - chunk),
                    (unsigned)g_last_error);
        check(ok, "throughput: a stop-and-wait DATA was not credited");
        if (ok) {
            const double rate = (double)(first - 4u * PERIOD_SIZE) / elapsed;
            fprintf(stderr, "throughput: stop-and-wait credit rate %.0f frames/s\n",
                    rate);
            /* Serviced only once per 2048-frame period, the sink admits one
             * 512-frame write per period: ~12 kframes/s, which starves the
             * SDK.  Real time is 48 kframes/s. */
            check(rate >= 0.9 * DEFAULT_RATE,
                  "throughput: a stop-and-wait producer was credited below real time");
        }
        check(cl_finish(fd, epoch, 1u, first, seq - 1u) == 0,
              "throughput: FINISH send failed");
        check(wait_event(ev, 'C', 8000) == 0,
              "throughput: completed generation never closed the PCM");
        close(fd);
    }
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "throughput: engine log missing");
    check(g_log.audit_denied == 0u,
          "throughput: the loop reached an external /sys /dev /run /data path");
}

/* Hardware start: a 3072-frame S32 ring, 2048-frame periods, and a mixer
 * stall (codec verify + unmute) after the first period.  A Sendspin-only
 * session has no FIFO input, so a loop that still waits the 20 ms FIFO poll
 * every period lets that first period drain dry: an XRUN on the Radar
 * ("PCM write failed ... Broken pipe") that ends the generation.  The
 * producer keeps the sink fed well ahead, as the SDK does. */
static void scen_rtstart(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, fd;
    uint32_t epoch = 0, status = 0, seq = 0;
    uint64_t first = 0;
    const uint32_t chunk = 512u;
    double start = 0.0;

    make_root(base, g_scen_names[SCEN_RTSTART], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    if (spawn(root, SCEN_RTSTART, &pid, &ev, &ctl) != 0) {
        check(0, "rtstart: spawn failed");
        return;
    }
    fd = connect_client(sock, 3000);
    check(fd >= 0, "rtstart: connect failed");
    if (fd >= 0) {
        int ok = 1;

        check(cl_open(fd, 1u, &epoch, &status) == 0 && status == 0u,
              "rtstart: OPEN failed");
        start = mono_seconds();
        while (ok && mono_seconds() - start < 1.0) {
            ok = cl_data_until_credit(fd, epoch, seq++, first, chunk) == 0;
            first += chunk;
        }
        fprintf(stderr, "rtstart: credited %llu frames in %.2f s over %u DATA offers\n",
                (unsigned long long)first, mono_seconds() - start, (unsigned)seq);
        check(ok, "rtstart: the engine stopped crediting a fed generation (XRUN fence?)");
        check(cl_finish(fd, epoch, 1u, first, seq - 1u) == 0,
              "rtstart: FINISH send failed");
        check(wait_event(ev, 'C', 8000) == 0,
              "rtstart: completed generation never closed the PCM");
        close(fd);
    }
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "rtstart: engine log missing");
    fprintf(stderr, "rtstart: %u underrun(s)\n", (unsigned)g_log.rt_underruns);
    check(g_log.rt_underruns == 0u,
          "rtstart: a fed Sendspin session let the S32 ring run dry after start");
    check(g_log.audit_denied == 0u,
          "rtstart: the loop reached an external /sys /dev /run /data path");
}

/* An idle engine must answer the companion promptly: its control ops are
 * bounded at a few tens of ms.  Polling only the source FIFOs leaves a
 * request waiting for the next 20 ms tick; the idle wait must also wake on
 * Sendspin socket activity.  PROGRESS_REQ for no generation draws an ERROR
 * without starting the PCM, so every sample is an idle round trip. */
static void scen_idlewake(const char *base)
{
    char root[600];
    char sock[700];
    pid_t pid;
    int ev, ctl, fd, i;
    double worst = 0.0, total = 0.0;
    const int samples = 16;

    make_root(base, g_scen_names[SCEN_IDLEWAKE], root, sizeof(root));
    (void)snprintf(sock, sizeof(sock), "%s/sendspin.sock", root);
    if (spawn(root, SCEN_IDLEWAKE, &pid, &ev, &ctl) != 0) {
        check(0, "idlewake: spawn failed");
        return;
    }
    fd = connect_client(sock, 3000);
    check(fd >= 0, "idlewake: connect failed");
    if (fd >= 0) {
        int ok = 1;

        for (i = 0; ok && i < samples; ++i) {
            uint8_t p[LE_AUDIO_SINK_PROGRESS_REQ_PAYLOAD_BYTES];
            uint8_t t = 0;
            uint8_t r[64];
            uint32_t rl = 0;
            double t0, dt;

            /* Spread requests across the engine's 20 ms poll phase. */
            usleep(7000u + (unsigned)i * 1300u);
            memset(p, 0, sizeof(p));
            t0 = mono_seconds();
            ok = send_datagram(fd, LE_AUDIO_SINK_TYPE_PROGRESS_REQ, p,
                               sizeof(p)) == 0 &&
                 recv_datagram(fd, &t, r, &rl) == 0;
            dt = mono_seconds() - t0;
            total += dt;
            if (dt > worst)
                worst = dt;
        }
        check(ok, "idlewake: an idle control request got no reply");
        if (ok) {
            fprintf(stderr, "idlewake: idle round trip mean %.2f ms worst %.2f ms\n",
                    total * 1000.0 / samples, worst * 1000.0);
            check(worst < 0.008,
                  "idlewake: idle engine answered the companion on its poll tick, not on socket activity");
        }
        close(fd);
    }
    (void)finish_child(pid, ev, ctl);
    check(load_log(root) == 0, "idlewake: engine log missing");
    check(g_log.audit_denied == 0u,
          "idlewake: the loop reached an external /sys /dev /run /data path");
}

static void scen_wide_epipe(const char *base)
{
    scen_xrun(base, SCEN_WIDE_EPIPE, 'F', "wideepipe");
    checkf("wideepipe", "recovery did not reopen the PCM as S32_LE",
           count_tag(T_PCM_WIDE_OPEN) >= 2 && count_tag(T_PCM_WIDE_REJECT) == 0);
}

struct loop_scenario {
    const char *name;
    void (*run)(const char *);
};

/* Every scenario is first-class and always runs unless one is named on the
 * command line; there is no silent skip. */
static const struct loop_scenario g_loop_scenarios[] = {
    { "prime", scen_prime },
    { "finish", scen_finish },
    { "legacy", scen_legacy },
    { "epipe", scen_epipe },
    { "estripe", scen_estripe },
    { "restart", scen_restart },
    { "mixfail", scen_mixfail },
    { "prepfail", scen_prepfail },
    { "stop", scen_stop },
    { "media", scen_media },
    { "pcmfail", scen_pcmfail },
    { "notiming", scen_notiming },
    { "notiminglegacy", scen_notiming_legacy },
    { "queryfail", scen_queryfail },
    { "widefinish", scen_wide_finish },
    { "wideepipe", scen_wide_epipe },
    { "throughput", scen_throughput },
    { "idlewake", scen_idlewake },
    { "rtstart", scen_rtstart },
};

int main(int argc, char **argv)
{
    const unsigned int count =
        (unsigned int)(sizeof(g_loop_scenarios) / sizeof(g_loop_scenarios[0]));
    int selected = -1;
    unsigned int i;

    if (argc < 2) {
        fprintf(stderr, "usage: %s <scratch-base> [scenario]\n", argv[0]);
        return 2;
    }
    if (argc >= 3) {
        for (i = 0; i < count; ++i)
            if (strcmp(argv[2], g_loop_scenarios[i].name) == 0)
                selected = (int)i;
        if (selected < 0) {
            fprintf(stderr, "engine-loop: unknown scenario '%s'\n", argv[2]);
            return 2;
        }
    }
    signal(SIGPIPE, SIG_IGN);
    audit_selftest(argv[1]);
    g_profile_dir = getenv("LE_AUDIO_ENGINE_SENDSPIN_PROFILE_DIR");
    /* The loop scenarios bound pacing after a generation ends; the output
     * hold (unit-tested in engine-sendspin) would add seconds of silence. */
    g_sendspin_hold_us = 0;
    for (i = 0; i < count; ++i) {
        if (selected >= 0 && (int)i != selected)
            continue;
        g_loop_scenarios[i].run(argv[1]);
    }
    if (g_fail) {
        fprintf(stderr, "engine-loop: %d outer-loop checks failed\n", g_fail);
        return 1;
    }
    if (selected >= 0)
        printf("engine-loop: scenario %s PASS\n", argv[2]);
    else
        puts("engine-loop: real run_engine + fake PCM/mixer + real socket PASS");
    return 0;
}
