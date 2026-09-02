#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <unistd.h>
#include <stddef.h>

static unsigned long n_malloc, n_free;
static char buf[256];
static void *(*real_malloc)(size_t);
static void  (*real_free)(void *);

void *malloc(size_t n)
{
    if (!real_malloc) real_malloc = dlsym(RTLD_NEXT, "malloc");
    n_malloc++;
    int len = snprintf(buf, sizeof buf, "[preload] malloc(%zu)\n", n);
    write(2, buf, len);
    return real_malloc(n);
}

void free(void *p)
{
    if (!real_free) real_free = dlsym(RTLD_NEXT, "free");
    n_free++;
    int len = snprintf(buf, sizeof buf, "[preload] free\n");
    write(2, buf, len);
    real_free(p);
}

__attribute__((destructor))
static void report(void)
{
    int len = snprintf(buf, sizeof buf,
                       "[preload] TOTAL intercepted: %lu malloc, %lu free\n",
                       n_malloc, n_free);
    write(2, buf, len);
}
