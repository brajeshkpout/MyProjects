#include "workers.h"
#include "ipc_common.h"

#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>

static volatile sig_atomic_t keep_running = 1;

static void handle_term(int sig) {
    (void)sig;
    keep_running = 0;
}

static int count_occupied(shared_state_t *st) {
    int n = 0;
    for (int i = 0; i < PHYSICAL_FRAMES; i++) {
        if (st->frame_table[i].occupied) n++;
    }
    return n;
}

void monitor_main(int shmid, int semid) {
    signal(SIGTERM, handle_term);

    shared_state_t *st = shmat(shmid, NULL, 0);
    if (st == (void *)-1) {
        perror("monitor: shmat");
        return;
    }

    while (keep_running) {
        sleep(1);
        if (!keep_running) break;

        sem_lock(semid, SEM_MUTEX_IDX);
        unsigned long acc = st->total_accesses;
        unsigned long flt = st->total_page_faults;
        unsigned long vio = st->total_violations;
        int used = count_occupied(st);
        sem_unlock(semid, SEM_MUTEX_IDX);

        printf("[monitor] accesses=%-4lu page_faults=%-4lu violations=%-4lu frames=%d/%d\n",
                acc, flt, vio, used, PHYSICAL_FRAMES);
        fflush(stdout);
    }

    shmdt(st);
}
