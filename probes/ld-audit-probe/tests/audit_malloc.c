#define _GNU_SOURCE
#include <link.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>

static unsigned long n_malloc, n_free;
static char buf[256];

static void note(const char *s, size_t n)
{
    int len = snprintf(buf, sizeof buf, "[my_malloc] %s(%zu)\n", s, n);
    write(2, buf, len);
}

/* our replacement allocator: uses the AUDIT namespace's libc malloc */
static void *my_malloc(size_t n) { n_malloc++; note("malloc", n); return malloc(n); }
static void  my_free(void *p)    { n_free++;   note("free", 0);   free(p); }

unsigned int la_version(unsigned int v) { return v; }

unsigned int la_objopen(struct link_map *map, Lmid_t lmid, uintptr_t *cookie)
{
    *cookie = (uintptr_t)map;
    return LA_FLG_BINDTO | LA_FLG_BINDFROM;
}

uintptr_t la_symbind64(Elf64_Sym *sym, unsigned int ndx,
                       uintptr_t *refcook, uintptr_t *defcook,
                       unsigned int *flags, const char *symname)
{
    struct link_map *from = (struct link_map *)*refcook;
    const char *who = (from && from->l_name[0]) ? from->l_name : "<main>";

    *flags |= LA_SYMB_NOPLTENTER | LA_SYMB_NOPLTEXIT;

    if (!strcmp(symname, "malloc")) {
        int len = snprintf(buf, sizeof buf, "[audit] REDIRECT malloc from %s\n", who);
        write(2, buf, len);
        return (uintptr_t)my_malloc;
    }
    if (!strcmp(symname, "free")) {
        int len = snprintf(buf, sizeof buf, "[audit] REDIRECT free from %s\n", who);
        write(2, buf, len);
        return (uintptr_t)my_free;
    }
    return sym->st_value;
}

__attribute__((destructor))
static void report(void)
{
    int len = snprintf(buf, sizeof buf,
                       "[audit] TOTAL intercepted: %lu malloc, %lu free\n",
                       n_malloc, n_free);
    write(2, buf, len);
}
