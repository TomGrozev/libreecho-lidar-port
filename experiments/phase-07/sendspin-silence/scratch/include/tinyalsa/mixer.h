#ifndef TINYALSA_MIXER_H
#define TINYALSA_MIXER_H
struct mixer;
struct mixer_ctl;
struct mixer *mixer_open(unsigned int card);
void mixer_close(struct mixer *mixer);
struct mixer_ctl *mixer_get_ctl_by_name(struct mixer *mixer, const char *name);
int mixer_ctl_set_enum_by_string(struct mixer_ctl *ctl, const char *value);
unsigned int mixer_ctl_get_num_values(struct mixer_ctl *ctl);
int mixer_ctl_set_value(struct mixer_ctl *ctl, unsigned int index, int value);
int mixer_ctl_get_value(struct mixer_ctl *ctl, unsigned int index);
#endif
