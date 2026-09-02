#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void)
{
    /* 1. direct call from the main binary */
    void *a = malloc(64);

    /* 2. libc-internal allocation: strdup mallocs inside libc */
    char *s = strdup("hello from strdup");

    /* 3. libc-internal allocation: stdio buffer + asprintf */
    char *t = NULL;
    if (asprintf(&t, "asprintf %d", 42) < 0) return 1;

    /* 4. C++-style / indirect: realloc + calloc */
    void *c = calloc(8, 8);

    fprintf(stderr, "prog: a=%p s=%s t=%s c=%p\n", a, s, t, c);

    free(a); free(s); free(t); free(c);
    return 0;
}
