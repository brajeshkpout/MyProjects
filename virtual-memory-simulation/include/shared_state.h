#ifndef SHARED_STATE_H
#define SHARED_STATE_H

#include <sys/types.h>
#include "config.h"

typedef enum { PERM_RO = 0, PERM_RW = 1 } permission_t;

/* One entry per virtual page, per process. Lives in shared memory so the
 * MMU process (writer) and the monitor process (reader) both see it. */
typedef struct {
    int            valid;             /* 1 = resident in a physical frame */
    int            frame_no;          /* -1 if not resident               */
    int            dirty;
    permission_t   permission;
    long           last_access_time;  /* logical clock tick (for LRU)      */
} page_table_entry_t;

/* One entry per physical frame. */
typedef struct {
    int  occupied;
    int  owner_proc_index;  /* -1 if free */
    int  page_no;
    long load_time;
    long last_access_time;
} frame_entry_t;

typedef struct {
    page_table_entry_t page_table[MAX_PROCESSES][VIRTUAL_PAGES_PER_PROC];
    frame_entry_t       frame_table[PHYSICAL_FRAMES];

    long global_clock;           /* logical timestamp, incremented on every access */
    unsigned long total_accesses;
    unsigned long total_page_faults;
    unsigned long total_violations;
    int active_processes;
} shared_state_t;

#endif /* SHARED_STATE_H */
