#ifndef WORKERS_H
#define WORKERS_H

/* Memory Management Unit: owns page tables + frame table, resolves faults,
 * enforces permissions, does global-LRU eviction, writes the shared log. */
void mmu_main(int shmid, int semid, int req_qid, int resp_qid);

/* Simulated user process: generates a stream of memory accesses (mostly
 * within a per-process working set, occasionally out-of-range) and talks
 * to the MMU over the message queues. */
void process_main(int proc_index, int num_accesses, int req_qid, int resp_qid, int semid);

/* Monitor: periodically snapshots shared_state_t (under the mutex
 * semaphore) and prints live stats to stdout. Stops on SIGTERM. */
void monitor_main(int shmid, int semid);

#endif /* WORKERS_H */
