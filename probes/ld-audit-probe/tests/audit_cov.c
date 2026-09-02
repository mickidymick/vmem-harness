/* Coverage test: can an auditor intercept EVERY allocation, including
 * libc-internal ones (strdup/asprintf)?  On glibc 2.31 it could not,
 * because libc reaches malloc/free via R_X86_64_GLOB_DAT and symbind
 * was only invoked for PLT (JUMP_SLOT) bindings. */
#define _GNU_SOURCE
#include <link.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>

static unsigned long n_malloc, n_free, n_calloc, n_realloc;
static unsigned long saw_malloc_binding_from_libc;

/* link_maps belonging to namespace 0 (the auditee). Only redirect calls
 * originating there -- never our own namespace, or we recurse. */
#define MAXOBJ 64
static struct link_map *ns0[MAXOBJ];
static int n_ns0;

static int in_ns0(struct link_map *m)
{
    for (int i = 0; i < n_ns0; i++) if (ns0[i] == m) return 1;
    return 0;
}

static void say(const char *fmt, const char *a, const char *b)
{
    char buf[300];
    int n = snprintf(buf, sizeof buf, fmt, a, b);
    write(2, buf, n);
}

/* replacement allocators -- these use the AUDIT namespace's libc */
static void *my_malloc(size_t n)          { n_malloc++;  return malloc(n); }
static void  my_free(void *p)             { n_free++;    free(p); }
static void *my_calloc(size_t a, size_t b){ n_calloc++;  return calloc(a, b); }
static void *my_realloc(void *p, size_t n){ n_realloc++; return realloc(p, n); }

unsigned int la_version(unsigned int v) { return v; }

unsigned int la_objopen(struct link_map *map, Lmid_t lmid, uintptr_t *cookie)
{
    *cookie = (uintptr_t)map;
    if (lmid == LM_ID_BASE && n_ns0 < MAXOBJ) ns0[n_ns0++] = map;
    return LA_FLG_BINDTO | LA_FLG_BINDFROM;
}

uintptr_t la_symbind64(Elf64_Sym *sym, unsigned int ndx,
                       uintptr_t *refcook, uintptr_t *defcook,
                       unsigned int *flags, const char *symname)
{
    struct link_map *from = (struct link_map *)*refcook;
    const char *who = (from && from->l_name[0]) ? from->l_name : "<main>";

    *flags |= LA_SYMB_NOPLTENTER | LA_SYMB_NOPLTEXIT;

    int interesting = !strcmp(symname, "malloc")  || !strcmp(symname, "free") ||
                      !strcmp(symname, "calloc")  || !strcmp(symname, "realloc");

    if (interesting) {
        say("[audit] binding reported: %-8s from %s\n", symname, who);
        if (strstr(who, "libc.so") && !strcmp(symname, "malloc"))
            saw_malloc_binding_from_libc = 1;
    }

    if (!interesting || !in_ns0(from)) return sym->st_value;

    if (!strcmp(symname, "malloc"))  return (uintptr_t)my_malloc;
    if (!strcmp(symname, "free"))    return (uintptr_t)my_free;
    if (!strcmp(symname, "calloc"))  return (uintptr_t)my_calloc;
    if (!strcmp(symname, "realloc")) return (uintptr_t)my_realloc;
    return sym->st_value;
}

__attribute__((destructor))
static void report(void)
{
    char buf[400];
    int n = snprintf(buf, sizeof buf,
        "\n[audit] ---- RESULT ----\n"
        "[audit] malloc=%lu free=%lu calloc=%lu realloc=%lu\n"
        "[audit] symbind reported a malloc binding FROM libc: %s\n",
        n_malloc, n_free, n_calloc, n_realloc,
        saw_malloc_binding_from_libc ? "YES" : "NO");
    write(2, buf, n);
}
