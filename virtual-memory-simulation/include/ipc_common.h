#ifndef IPC_COMMON_H
#define IPC_COMMON_H

#include <sys/types.h>
#include <sys/ipc.h>
#include <sys/msg.h>
#include <sys/sem.h>
#include <sys/shm.h>

#include "config.h"
#include "shared_state.h"

/* ---- Semaphore set layout ---- */
#define SEM_MUTEX_IDX 0   /* protects shared_state_t reads/writes         */
#define SEM_SLOTS_IDX 1   /* counting semaphore: bounds in-flight requests */
#define SEM_COUNT     2

#define SHUTDOWN_PROC_INDEX (-1)

typedef enum { ACCESS_READ = 0, ACCESS_WRITE = 1 } access_type_t;

typedef enum {
    RESP_OK = 0,
    RESP_FAULT_RESOLVED = 1,
    RESP_PROTECTION_VIOLATION = 2,
    RESP_SEGMENTATION_FAULT = 3
} resp_status_t;

/* Sent by worker processes to the MMU. All requests share mtype = 1 so the
 * MMU can drain them strictly in send order with msgrcv(..., 0, ...). */
typedef struct {
    long          mtype;
    int           proc_index;   /* SHUTDOWN_PROC_INDEX requests MMU exit */
    pid_t         pid;
    unsigned long vaddr;
    access_type_t access_type;
    int           seq;
} request_msg_t;

/* Sent by the MMU back to the originating process. mtype = proc_index + 1
 * so each worker can select only its own reply out of the queue. */
typedef struct {
    long          mtype;
    int           proc_index;
    unsigned long paddr;
    resp_status_t status;
    int           seq;
    int           evicted_frame; /* -1 if no eviction occurred */
} response_msg_t;

#if defined(__linux__)
/* glibc does not define this union for us (POSIX leaves it to the caller). */
union semun {
    int              val;
    struct semid_ds *buf;
    unsigned short  *array;
    struct seminfo  *__buf;
};
#endif

key_t make_key(char proj_id);

int get_shm_segment(int create);
int get_sem_set(int create);
int get_req_queue(int create);
int get_resp_queue(int create);

void sem_lock(int semid, int idx);
void sem_unlock(int semid, int idx);
void sem_wait_n(int semid, int idx);
void sem_post_n(int semid, int idx);

#endif /* IPC_COMMON_H */
