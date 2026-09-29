#include "ipc_common.h"
#include "workers.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <sys/wait.h>
#include <sys/stat.h>

static void print_usage(const char *prog) {
    fprintf(stderr,
        "Usage: %s [num_processes] [accesses_per_process]\n"
        "  num_processes         1..%d (default %d)\n"
        "  accesses_per_process  default %d\n",
        prog, MAX_PROCESSES, DEFAULT_NUM_PROCESSES, DEFAULT_ACCESSES);
}

int main(int argc, char **argv) {
    int num_processes = DEFAULT_NUM_PROCESSES;
    int num_accesses  = DEFAULT_ACCESSES;

    if (argc > 1) num_processes = atoi(argv[1]);
    if (argc > 2) num_accesses  = atoi(argv[2]);

    if (num_processes < 1 || num_processes > MAX_PROCESSES || num_accesses < 1) {
        print_usage(argv[0]);
        return 1;
    }

    mkdir("logs", 0755); /* ignore EEXIST */
    FILE *trunc = fopen(LOG_FILE_PATH, "w");
    if (trunc) fclose(trunc);

    printf("===================================================\n");
    printf(" Virtual Memory Simulation (demand paging + LRU)\n");
    printf("===================================================\n");
    printf(" processes           : %d\n", num_processes);
    printf(" accesses/process    : %d\n", num_accesses);
    printf(" virtual pages/proc  : %d (%u KB)\n", VIRTUAL_PAGES_PER_PROC,
            VIRTUAL_PAGES_PER_PROC * PAGE_SIZE / 1024);
    printf(" physical frames     : %d (%u KB)\n", PHYSICAL_FRAMES,
            PHYSICAL_FRAMES * PAGE_SIZE / 1024);
    printf(" read-only pages     : first %d pages of each process\n", CODE_PAGES_RO);
    printf(" log file            : %s\n", LOG_FILE_PATH);
    printf("---------------------------------------------------\n");
    fflush(stdout); /* flush before forking so children don't inherit and
                      * re-emit this buffered text when they later flush */

    int shmid  = get_shm_segment(1);
    int semid  = get_sem_set(1);
    int reqq   = get_req_queue(1);
    int respq  = get_resp_queue(1);

    union semun su;
    su.val = 1;
    if (semctl(semid, SEM_MUTEX_IDX, SETVAL, su) == -1) { perror("semctl mutex init"); return 1; }
    su.val = MAX_INFLIGHT_REQUESTS;
    if (semctl(semid, SEM_SLOTS_IDX, SETVAL, su) == -1) { perror("semctl slots init"); return 1; }

    pid_t mmu_pid = fork();
    if (mmu_pid < 0) { perror("fork mmu"); return 1; }
    if (mmu_pid == 0) {
        mmu_main(shmid, semid, reqq, respq);
        _exit(0);
    }

    /* Give the MMU a brief moment to initialize the tables before workers
     * start hammering it; harmless if it's already ready. */
    usleep(50000);

    pid_t monitor_pid = fork();
    if (monitor_pid < 0) { perror("fork monitor"); }
    if (monitor_pid == 0) {
        monitor_main(shmid, semid);
        _exit(0);
    }

    pid_t worker_pids[MAX_PROCESSES];
    for (int i = 0; i < num_processes; i++) {
        pid_t p = fork();
        if (p < 0) { perror("fork worker"); continue; }
        if (p == 0) {
            process_main(i, num_accesses, reqq, respq, semid);
            _exit(0);
        }
        worker_pids[i] = p;
    }

    for (int i = 0; i < num_processes; i++) {
        waitpid(worker_pids[i], NULL, 0);
    }

    /* Tell the MMU to shut down; queue is FIFO so it drains any remaining
     * in-order requests before seeing this. */
    request_msg_t shut;
    memset(&shut, 0, sizeof(shut));
    shut.mtype = 1;
    shut.proc_index = SHUTDOWN_PROC_INDEX;
    msgsnd(reqq, &shut, sizeof(shut) - sizeof(long), 0);
    waitpid(mmu_pid, NULL, 0);

    if (monitor_pid > 0) {
        kill(monitor_pid, SIGTERM);
        waitpid(monitor_pid, NULL, 0);
    }

    shared_state_t *st = shmat(shmid, NULL, 0);
    printf("---------------------------------------------------\n");
    if (st != (void *)-1) {
        printf(" Total memory accesses : %lu\n", st->total_accesses);
        printf(" Total page faults     : %lu\n", st->total_page_faults);
        printf(" Total violations      : %lu\n", st->total_violations);
        shmdt(st);
    }
    printf("===================================================\n");
    printf("Full timestamped log written to %s\n", LOG_FILE_PATH);

    msgctl(reqq, IPC_RMID, NULL);
    msgctl(respq, IPC_RMID, NULL);
    semctl(semid, 0, IPC_RMID);
    shmctl(shmid, IPC_RMID, NULL);

    return 0;
}
