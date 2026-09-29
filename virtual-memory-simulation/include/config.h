#ifndef CONFIG_H
#define CONFIG_H

/* ---- Memory geometry ---- */
#define PAGE_SIZE               4096u   /* bytes per page/frame            */
#define VIRTUAL_PAGES_PER_PROC  64      /* -> 256 KB virtual space / proc  */
#define PHYSICAL_FRAMES         16      /* -> 64 KB physical memory total  */
#define CODE_PAGES_RO           4       /* first N pages = read-only code  */

/* ---- Workload ---- */
#define MAX_PROCESSES           8
#define DEFAULT_NUM_PROCESSES   4
#define DEFAULT_ACCESSES        40
#define WORKING_SET_SIZE        6
#define LOCALITY_BIAS_PERCENT   70      /* % of accesses inside working set */

/* ---- Synchronization ---- */
#define MAX_INFLIGHT_REQUESTS   4       /* counting semaphore capacity      */

/* ---- IPC key generation (ftok) ---- */
#define IPC_KEY_PATH     "."
#define IPC_PROJ_SHM     'S'
#define IPC_PROJ_SEM     'M'
#define IPC_PROJ_REQ_Q   'Q'
#define IPC_PROJ_RESP_Q  'R'

/* ---- Logging ---- */
#define LOG_FILE_PATH "logs/vm_simulation.log"

#endif /* CONFIG_H */
