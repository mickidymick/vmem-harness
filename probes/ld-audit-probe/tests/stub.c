/* Preloaded into the APP namespace. No-op definitions so the app's
 * references have something to bind to; the auditor rewrites them. */
#include <stdio.h>

int vmem_migrate_region_to_node(void *addr, int node)
{
    (void)addr; (void)node;
    fprintf(stderr, "  [stub] NOT redirected - stub ran\n");
    return -1;
}

int vmem_query_migrations(void)
{
    fprintf(stderr, "  [stub] NOT redirected - stub ran\n");
    return -1;
}
