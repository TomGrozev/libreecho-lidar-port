#ifndef TINYALSA_PCM_H
#define TINYALSA_PCM_H
#include <time.h>
#define PCM_OUT 0x00000000U
#define PCM_MONOTONIC 0x00000008U
#define PCM_NORESTART 0x00000004U
enum pcm_format { PCM_FORMAT_S16_LE = 0, PCM_FORMAT_S32_LE = 1 };
struct pcm_config {
    unsigned int channels;
    unsigned int rate;
    unsigned int period_size;
    unsigned int period_count;
    enum pcm_format format;
    unsigned int start_threshold;
    unsigned int stop_threshold;
    unsigned int silence_threshold;
    unsigned int silence_size;
    unsigned int avail_min;
};
struct pcm;
struct pcm *pcm_open(unsigned int card, unsigned int device, unsigned int flags,
                     const struct pcm_config *config);
int pcm_is_ready(struct pcm *pcm);
const char *pcm_get_error(struct pcm *pcm);
void pcm_close(struct pcm *pcm);
int pcm_prepare(struct pcm *pcm);
int pcm_writei(struct pcm *pcm, const void *data, unsigned int frame_count);
unsigned int pcm_get_buffer_size(const struct pcm *pcm);
int pcm_get_htimestamp(struct pcm *pcm, unsigned int *avail,
                       struct timespec *timestamp);
#endif
