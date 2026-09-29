#include "workers.h"
#include "ipc_common.h"

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>

void process_main(int proc_index, int num_accesses, int req_qid, int resp_qid, int semid) {
    srand((unsigned)(getpid() ^ time(NULL)));

    int working_set[WORKING_SET_SIZE];
    for (int i = 0; i < WORKING_SET_SIZE; i++) {
        working_set[i] = rand() % VIRTUAL_PAGES_PER_PROC;
    }

    int seq = 0;

    for (int i = 0; i < num_accesses; i++) {
        int page_no;
        if ((rand() % 100) < LOCALITY_BIAS_PERCENT) {
            /* stay inside the working set -> demonstrates LRU keeping hot pages resident */
            page_no = working_set[rand() % WORKING_SET_SIZE];
        } else {
            /* occasionally wander outside valid range -> demonstrates segfault handling
             * (small slack keeps this rare enough that workers usually finish their
             * full workload, while still exercising the segfault path over a run). */
            page_no = rand() % (VIRTUAL_PAGES_PER_PROC + 1);
        }

        unsigned long offset = (unsigned long)(rand() % PAGE_SIZE);
        unsigned long vaddr = (unsigned long)page_no * PAGE_SIZE + offset;

        access_type_t at = ACCESS_READ;
        if (page_no >= CODE_PAGES_RO) {
            at = ((rand() % 100) < 30) ? ACCESS_WRITE : ACCESS_READ;
        } else if ((rand() % 100) < 25) {
            /* occasionally try to write to a read-only "code" page on purpose,
             * to exercise the MMU's protection-violation path */
            at = ACCESS_WRITE;
        }

        sem_wait_n(semid, SEM_SLOTS_IDX);

        request_msg_t req;
        req.mtype = 1;
        req.proc_index = proc_index;
        req.pid = getpid();
        req.vaddr = vaddr;
        req.access_type = at;
        req.seq = seq;

        if (msgsnd(req_qid, &req, sizeof(req) - sizeof(long), 0) == -1) {
            perror("process: msgsnd");
            sem_post_n(semid, SEM_SLOTS_IDX);
            break;
        }

        response_msg_t resp;
        if (msgrcv(resp_qid, &resp, sizeof(resp) - sizeof(long), proc_index + 1, 0) == -1) {
            perror("process: msgrcv");
            sem_post_n(semid, SEM_SLOTS_IDX);
            break;
        }

        sem_post_n(semid, SEM_SLOTS_IDX);

        if (resp.status == RESP_SEGMENTATION_FAULT) {
            fprintf(stderr, "[proc %d pid=%d] segmentation fault at vaddr=%lu — terminating\n",
                    proc_index, getpid(), vaddr);
            break;
        }
        if (resp.status == RESP_PROTECTION_VIOLATION) {
            fprintf(stderr, "[proc %d pid=%d] protection violation (write to RO page) at vaddr=%lu\n",
                    proc_index, getpid(), vaddr);
        }

        seq++;
        usleep(1000 + (rand() % 3000)); /* stagger requests so processes interleave */
    }

    printf("[proc %d pid=%d] finished (%d accesses attempted)\n", proc_index, getpid(), seq);
    fflush(stdout); /* worker exits via _exit() in the launcher, which skips stdio flushing */
}
