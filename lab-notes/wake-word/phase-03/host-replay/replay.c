/*
 * Host replay through the waked decode path: real microWakeWord engine plus
 * the real wake_worker decision rule, over raw mono S16_LE 16 kHz PCM.
 *
 * usage: replay <wakeword-models>/<word> <raw.pcm>
 * Prints one line per detection and a final "detections N dropped N" line.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "adapter/wake_worker.h"

#define BLOCK 1280U /* 80 ms at 16 kHz */

static unsigned int detections;

static void nap_ms(long ms) {
  struct timespec delay = {ms / 1000, (ms % 1000) * 1000000L};
  nanosleep(&delay, NULL);
}

static void on_event(const struct le_wake_event *event, void *opaque) {
  (void)opaque;
  ++detections;
  printf("event %u sample %llu score %.4f vad %.4f\n", detections,
         (unsigned long long)event->detection_sample, event->score,
         event->vad_score);
}

int main(int argc, char **argv) {
  struct le_wake_worker worker = {NULL};
  struct le_wake_worker_metrics metrics;
  struct le_wake_observation observation = {0, 1.0f, 1, 0};
  int16_t block[BLOCK];
  size_t got;
  uint64_t position = 0;
  FILE *pcm;

  if (argc != 3) {
    fprintf(stderr, "usage: %s <word-directory> <raw.pcm>\n", argv[0]);
    return 2;
  }
  pcm = fopen(argv[2], "rb");
  if (!pcm) {
    perror(argv[2]);
    return 2;
  }
  if (le_wake_worker_start(&worker, argv[1], 1, LE_WAKE_DEFAULT_SENSITIVITY,
                           on_event, NULL) != 0) {
    fprintf(stderr, "start failed\n");
    fclose(pcm);
    return 1;
  }
  while ((got = fread(block, sizeof(block[0]), BLOCK, pcm)) > 0) {
    memset(block + got, 0, (BLOCK - got) * sizeof(block[0]));
    observation.detection_sample = position;
    position += got;
    while (le_wake_worker_submit(&worker, block, BLOCK, &observation) != 0)
      nap_ms(2);
    nap_ms(3); /* inference takes ~2 ms; keep the 8-block queue drained */
  }
  fclose(pcm);
  { /* one padded silence block, as ESPHome appends after a clip */
    static int16_t silence[BLOCK];
    observation.detection_sample = position;
    le_wake_worker_submit(&worker, silence, BLOCK, &observation);
  }
  nap_ms(1000);
  le_wake_worker_stop(&worker, &metrics);
  printf("detections %u dropped %llu\n", detections,
         (unsigned long long)metrics.dropped_blocks);
  return metrics.dropped_blocks != 0;
}
