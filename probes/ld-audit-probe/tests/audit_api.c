#define _GNU_SOURCE
#include <link.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>

/* ---- state that lives ONLY in the audit namespace ---- */
static int   migrations;
static void *heap_marker;

static void say(const char *m)
{
    char b[200]; int n = snprintf(b, sizeof b, "%s", m); write(2, b, n);
}

/* real implementations, in the audit namespace */
static int real_migrate(void *addr, int node)
{
    char b[200];
    migrations++;
    int n = snprintf(b, sizeof b,
        "  [audit-ns] real_migrate(addr=%p, node=%d)  migrations=%d\n",
        addr, node, migrations);
    write(2, b, n);
    return 0;
}

static int real_query(void) { return migrations; }

unsigned int la_version(unsigned int v)
{
    heap_marker = malloc(32);           /* audit namespace's heap */
    char b[120];
    int n = snprintf(b, sizeof b, "[audit-ns] my heap: %p\n", heap_marker);
    write(2, b, n);
    return v;
}

unsigned int la_objopen(struct link_map *map, Lmid_t lmid, uintptr_t *cookie)
{
    *cookie = (uintptr_t)map;
    return LA_FLG_BINDTO | LA_FLG_BINDFROM;
}

uintptr_t la_symbind64(Elf64_Sym *sym, unsigned int ndx,
                       uintptr_t *refcook, uintptr_t *defcook,
                       unsigned int *flags, const char *symname)
{
    *flags |= LA_SYMB_NOPLTENTER | LA_SYMB_NOPLTEXIT;

    if (!strcmp(symname, "vmem_migrate_region_to_node")) {
        say("[audit] rebinding vmem_migrate_region_to_node -> audit namespace\n");
        return (uintptr_t)real_migrate;
    }
    if (!strcmp(symname, "vmem_query_migrations")) {
        say("[audit] rebinding vmem_query_migrations -> audit namespace\n");
        return (uintptr_t)real_query;
    }
    return sym->st_value;
}
