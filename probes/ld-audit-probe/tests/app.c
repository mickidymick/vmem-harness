#include <stdio.h>
#include <stdlib.h>

extern int vmem_migrate_region_to_node(void *addr, int node);
extern int vmem_query_migrations(void);

int main(void)
{
    void *p = malloc(4096);
    printf("app: heap %p\n", p);

    printf("app: migrate -> %d\n", vmem_migrate_region_to_node(p, 1));
    printf("app: migrate -> %d\n", vmem_migrate_region_to_node(p, 0));
    printf("app: query   -> %d  (expect 2 if state is shared)\n",
           vmem_query_migrations());
    return 0;
}
