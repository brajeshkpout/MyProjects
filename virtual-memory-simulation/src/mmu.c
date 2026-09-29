#include "workers.h"
#include "ipc_common.h"
#include "shared_state.h"
#include "logger.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>

/* Returns index of a free frame, or -1 if none is free. */
static int find_free_frame(shared_state_t *st) {
    for (int i = 0; i < PHYSICAL_FRAMES; i++) {
        if (!st->frame_table[i].occupied) return i;
    }
    return -1;
}

/* Global LRU: the frame whose last_access_time is smallest across the
 * *entire* physical memory (not per-process), matching the multiprogramming
 * requirement of optimizing shared resource utilization. */
static int find_lru_frame(shared_state_t *st) {
    int victim = 0;
    long oldest = st->frame_table[0].last_access_time;
    for (int i = 1; i < PHYSICAL_FRAMES; i++) {
        if (st->frame_table[i].last_access_time < oldest) {
            oldest = st->frame_table[i].last_access_time;
            victim = i;
        }
    }
    return victim;
}

static void init_tables(shared_state_t *st) {
    memset(st, 0, sizeof(*st));
    for (int p = 0; p < MAX_PROCESSES; p++) {
        for (int pg = 0; pg < VIRTUAL_PAGES_PER_PROC; pg++) {
            st->page_table[p][pg].valid = 0;
            st->page_table[p][pg].frame_no = -1;
        }
    }
    for (int f = 0; f < PHYSICAL_FRAMES; f++) {
        st->frame_table[f].occupied = 0;
        st->frame_table[f].owner_proc_index = -1;
        st->frame_table[f].page_no = -1;
    }
}

void mmu_main(int shmid, int semid, int req_qid, int resp_qid) {
    shared_state_t *st = shmat(shmid, NULL, 0);
    if (st == (void *)-1) {
        perror("mmu: shmat");
        exit(1);
    }

    logger_init(LOG_FILE_PATH);
    log_line("MMU: online. %d physical frames, %d virtual pages/process, first %d pages RO.",
              PHYSICAL_FRAMES, VIRTUAL_PAGES_PER_PROC, CODE_PAGES_RO);

    sem_lock(semid, SEM_MUTEX_IDX);
    init_tables(st);
    sem_unlock(semid, SEM_MUTEX_IDX);

    for (;;) {
        request_msg_t req;
        ssize_t r = msgrcv(req_qid, &req, sizeof(req) - sizeof(long), 0, 0);
        if (r == -1) {
            if (errno == EINTR) continue;
            perror("mmu: msgrcv");
            break;
        }

        if (req.proc_index == SHUTDOWN_PROC_INDEX) {
            log_line("MMU: shutdown signal received. Halting.");
            break;
        }

        response_msg_t resp;
        resp.mtype = req.proc_index + 1;
        resp.proc_index = req.proc_index;
        resp.seq = req.seq;
        resp.evicted_frame = -1;

        sem_lock(semid, SEM_MUTEX_IDX);

        int page_no = (int)(req.vaddr / PAGE_SIZE);

        if (page_no < 0 || page_no >= VIRTUAL_PAGES_PER_PROC) {
            resp.status = RESP_SEGMENTATION_FAULT;
            resp.paddr = 0;
            st->total_violations++;
            log_line("SEGFAULT   proc=%d pid=%d vaddr=%lu (page %d out of range [0,%d))",
                      req.proc_index, req.pid, req.vaddr, page_no, VIRTUAL_PAGES_PER_PROC);
        } else {
            page_table_entry_t *pte = &st->page_table[req.proc_index][page_no];

            if (!pte->valid) {
                /* ---- Page fault: bring the page in ---- */
                st->total_page_faults++;

                int frame_no = find_free_frame(st);
                if (frame_no == -1) {
                    frame_no = find_lru_frame(st);
                    frame_entry_t *victim = &st->frame_table[frame_no];
                    resp.evicted_frame = frame_no;

                    log_line("EVICT      frame=%d victim_proc=%d victim_page=%d (LRU, age=%ld) to load proc=%d page=%d",
                              frame_no, victim->owner_proc_index, victim->page_no,
                              st->global_clock - victim->last_access_time,
                              req.proc_index, page_no);

                    st->page_table[victim->owner_proc_index][victim->page_no].valid = 0;
                    st->page_table[victim->owner_proc_index][victim->page_no].frame_no = -1;
                }

                st->global_clock++;
                pte->valid = 1;
                pte->frame_no = frame_no;
                pte->dirty = 0;
                pte->permission = (page_no < CODE_PAGES_RO) ? PERM_RO : PERM_RW;
                pte->last_access_time = st->global_clock;

                st->frame_table[frame_no].occupied = 1;
                st->frame_table[frame_no].owner_proc_index = req.proc_index;
                st->frame_table[frame_no].page_no = page_no;
                st->frame_table[frame_no].load_time = st->global_clock;
                st->frame_table[frame_no].last_access_time = st->global_clock;

                resp.status = RESP_FAULT_RESOLVED;
                resp.paddr = (unsigned long)frame_no * PAGE_SIZE + (req.vaddr % PAGE_SIZE);

                log_line("PAGE_FAULT proc=%d pid=%d vaddr=%lu page=%d -> frame=%d perm=%s",
                          req.proc_index, req.pid, req.vaddr, page_no, frame_no,
                          pte->permission == PERM_RO ? "RO" : "RW");

            } else if (req.access_type == ACCESS_WRITE && pte->permission == PERM_RO) {
                /* ---- Protection violation ---- */
                st->total_violations++;
                resp.status = RESP_PROTECTION_VIOLATION;
                resp.paddr = 0;
                log_line("VIOLATION  proc=%d pid=%d vaddr=%lu page=%d WRITE denied (page is read-only)",
                          req.proc_index, req.pid, req.vaddr, page_no);
            } else {
                /* ---- Normal hit ---- */
                st->global_clock++;
                pte->last_access_time = st->global_clock;
                st->frame_table[pte->frame_no].last_access_time = st->global_clock;
                if (req.access_type == ACCESS_WRITE) pte->dirty = 1;

                resp.status = RESP_OK;
                resp.paddr = (unsigned long)pte->frame_no * PAGE_SIZE + (req.vaddr % PAGE_SIZE);

                log_line("ACCESS     proc=%d pid=%d vaddr=%lu page=%d frame=%d %s",
                          req.proc_index, req.pid, req.vaddr, page_no, pte->frame_no,
                          req.access_type == ACCESS_WRITE ? "WRITE" : "READ");
            }

            st->total_accesses++;
        }

        sem_unlock(semid, SEM_MUTEX_IDX);

        if (msgsnd(resp_qid, &resp, sizeof(resp) - sizeof(long), 0) == -1) {
            perror("mmu: msgsnd");
        }
    }

    logger_close();
    shmdt(st);
}
