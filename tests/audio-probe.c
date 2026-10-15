/* Exercise the real ALSA default PCM through a dynamically loaded libasound.
 * No ALSA development headers are needed; compile both -m64 and -m32. */
#include <dlfcn.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    void *lib = dlopen("libasound.so.2", RTLD_NOW);
    if (!lib) { fprintf(stderr, "%s\n", dlerror()); return 1; }
    int (*open_pcm)(void **, const char *, int, int) = dlsym(lib, "snd_pcm_open");
    int (*params)(void *, int, int, unsigned, unsigned, int, unsigned) = dlsym(lib, "snd_pcm_set_params");
    long (*write_pcm)(void *, const void *, unsigned long) = dlsym(lib, "snd_pcm_writei");
    int (*drain)(void *) = dlsym(lib, "snd_pcm_drain");
    int (*close_pcm)(void *) = dlsym(lib, "snd_pcm_close");
    void *pcm = NULL;
    if (!open_pcm || !params || !write_pcm || !drain || !close_pcm) return 2;
    if (open_pcm(&pcm, "default", 0, 0) < 0) return 3;
    /* S16_LE, RW_INTERLEAVED, stereo, 48kHz. */
    if (params(pcm, 2, 3, 2, 48000, 1, 100000) < 0) return 4;
    int16_t samples[960];
    for (int block = 0; block < 150; block++) {
        for (int i = 0; i < 480; i++) {
            int16_t v = (int16_t)(12000 * sin(2 * 3.141592653589793 * 440 * (block * 480 + i) / 48000));
            samples[2*i] = samples[2*i+1] = v;
        }
        long n = 0;
        while (n < 480) {
            long written = write_pcm(pcm, samples + 2*n, 480 - n);
            if (written <= 0) return 5;
            n += written;
        }
    }
    drain(pcm); close_pcm(pcm); dlclose(lib);
    printf("ALSA default PCM played (%zu-bit)\n", sizeof(void *) * 8);
    return 0;
}
