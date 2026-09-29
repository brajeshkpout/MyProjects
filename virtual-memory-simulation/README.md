# Virtual Memory Simulation

A multi-process simulation of **demand-paged virtual memory** with **LRU page
replacement**, built in C using System V IPC (shared memory, message queues,
semaphores) on Linux.

Several simulated user processes each generate a stream of virtual memory
accesses. A dedicated **Memory Management Unit (MMU)** process owns the page
tables and physical frame table in shared memory, resolves page faults,
performs global-LRU eviction under memory pressure, enforces per-page
read/write permissions, and writes every access, fault, and violation to a
single timestamped log — all synchronized across processes with semaphores.

## Architecture

```
                 ┌─────────────────────┐
  worker procs   │   request queue     │        ┌────────────┐
  (0..N-1)  ───► │  (SysV msg queue)   │ ─────► │    MMU     │
                 └─────────────────────┘        │  process   │
                 ┌─────────────────────┐        │            │
  worker procs   │   response queue    │ ◄───── │ page table │
  (0..N-1)  ◄─── │  (SysV msg queue)   │        │ frame table│
                 └─────────────────────┘        └─────┬──────┘
                                                       │
                                            shared memory segment
                                          (page tables + frame table
                                           + global stats/clock)
                                                       │
                                                 ┌─────▼──────┐
                                                 │  monitor   │  (read-only,
                                                 │  process   │   periodic)
                                                 └────────────┘
```

- **Worker processes** (`process_main`, `src/process_sim.c`): each simulates
  a process with its own 256 KB virtual address space (64 pages × 4 KB).
  Accesses are drawn mostly from a small per-process "working set" (locality
  of reference) with an occasional wider excursion — this reliably produces
  both page faults and, when it wanders out of range, a segmentation fault,
  and it occasionally attempts an illegal write to a read-only page.

- **MMU process** (`mmu_main`, `src/mmu.c`): the single writer of the page
  tables and frame table. For every request it:
  1. Range-checks the virtual address (`SEGFAULT` if out of bounds).
  2. On a miss, takes a free frame or, if physical memory is full, evicts
     the **globally** least-recently-used frame (across *all* processes —
     this is what "optimizes resource utilization in multiprogramming
     environments": memory is a shared, contended resource, not partitioned
     per process).
  3. On a hit, checks permissions — the first `CODE_PAGES_RO` pages of every
     process are marked read-only (simulating a code segment); a write to
     one is a protection violation, not a crash.
  4. Updates the logical clock (used both for LRU ages and as an ordering
     signal) and appends a timestamped record to `logs/vm_simulation.log`.

- **Monitor process** (`monitor_main`, `src/monitor.c`): once a second, takes
  the shared-memory mutex, snapshots live counters (accesses / faults /
  violations / frames in use), and prints them — a second, independent
  reader synchronized against the MMU purely through the semaphore.

- **Launcher** (`main`, `src/launcher.c`): the single entry point. Creates
  all IPC resources, forks the MMU, the monitor, and every worker, waits for
  workers to finish, sends a shutdown message to the MMU, stops the monitor,
  prints a summary, and removes every IPC resource it created (no leaked
  shared memory/semaphores/queues, even across repeated runs).

### Synchronization

Two semaphores in one SysV semaphore set:

| Semaphore   | Purpose                                                        |
|-------------|-----------------------------------------------------------------|
| `SEM_MUTEX` | Binary mutex guarding all reads/writes of the shared page & frame tables (held by the MMU while resolving a request, and by the monitor while snapshotting stats). |
| `SEM_SLOTS` | Counting semaphore (default capacity 4) that each worker must acquire before sending a request and releases after receiving its reply — bounds the number of in-flight requests across all worker processes. |

### IPC summary

| Resource        | Key (via `ftok`) | Contents                                   |
|------------------|-----------------|---------------------------------------------|
| Shared memory   | proj id `'S'`    | `shared_state_t`: page tables, frame table, global clock, counters |
| Semaphore set   | proj id `'M'`    | mutex + slot-limiting semaphore              |
| Request queue   | proj id `'Q'`    | worker → MMU (`request_msg_t`, single `mtype=1`) |
| Response queue  | proj id `'R'`    | MMU → worker (`response_msg_t`, `mtype = proc_index+1`) |

## Building

Requires `gcc` and a Linux/POSIX environment (SysV IPC).

```bash
make
```

Produces a single binary, `vmsim`, that plays all three roles (MMU, monitor,
worker) by `fork()`-ing itself — no separate binaries to manage.

## Running

```bash
./vmsim [num_processes] [accesses_per_process]

# e.g.
./vmsim 6 80
```

Defaults to 4 processes × 40 accesses if no arguments are given.
`num_processes` must be between 1 and `MAX_PROCESSES` (8, see
`include/config.h`).

Console output shows live monitor snapshots and each worker's outcome
(segfault / protection violation / normal completion); the full,
timestamped, per-access trace is written to `logs/vm_simulation.log`.

### Sample console output

```
===================================================
 Virtual Memory Simulation (demand paging + LRU)
===================================================
 processes           : 6
 accesses/process    : 80
 virtual pages/proc  : 64 (256 KB)
 physical frames     : 16 (64 KB)
 read-only pages     : first 4 pages of each process
 log file            : logs/vm_simulation.log
---------------------------------------------------
[monitor] accesses=42   page_faults=38   violations=0    frames=16/16
[proc 2 pid=345] segmentation fault at vaddr=263200 — terminating
[proc 5 pid=348] protection violation (write to RO page) at vaddr=8296
[proc 3 pid=346] finished (80 accesses attempted)
...
---------------------------------------------------
 Total memory accesses : 380
 Total page faults     : 280
 Total violations      : 4
===================================================
Full timestamped log written to logs/vm_simulation.log
```

### Sample log entries

```
[2026-09-27 14:57:23.678205] EVICT      frame=1 victim_proc=1 victim_page=9 (LRU, age=17) to load proc=0 page=3
[2026-09-27 14:57:23.678208] PAGE_FAULT proc=0 pid=196 vaddr=15139 page=3 -> frame=1 perm=RO
[2026-09-27 14:57:23.816325] SEGFAULT   proc=2 pid=198 vaddr=271137 (page 66 out of range [0,64))
[2026-09-27 14:57:24.012004] VIOLATION  proc=5 pid=348 vaddr=8296 page=2 WRITE denied (page is read-only)
```

## Cleaning up

```bash
make clean       # remove build artifacts and logs
make ipc-clean   # remove any stale SysV IPC resources (only needed if a
                  # run was force-killed, e.g. `kill -9`, before it could
                  # clean up after itself)
```

## Tuning the simulation

All sizes and probabilities live in `include/config.h`:

| Constant                  | Meaning                                          |
|---------------------------|---------------------------------------------------|
| `VIRTUAL_PAGES_PER_PROC`  | Virtual address space size per process             |
| `PHYSICAL_FRAMES`         | Total physical memory shared by all processes      |
| `CODE_PAGES_RO`           | How many low pages are read-only per process       |
| `WORKING_SET_SIZE`        | Size of each worker's "hot" page set                |
| `LOCALITY_BIAS_PERCENT`   | % of accesses drawn from the working set            |
| `MAX_INFLIGHT_REQUESTS`   | Capacity of the request-throttling semaphore        |

Shrinking `PHYSICAL_FRAMES` relative to `VIRTUAL_PAGES_PER_PROC` and the
number of processes increases contention and demonstrates LRU eviction more
frequently; the defaults (16 frames shared across up to 8 processes with 64
pages each) are already deliberately over-subscribed.

## Project layout

```
.
├── Makefile
├── README.md
├── include/
│   ├── config.h          constants (sizes, keys, tunables)
│   ├── shared_state.h    shared-memory layout (page/frame tables)
│   ├── ipc_common.h      message formats + IPC helper declarations
│   ├── workers.h         mmu_main / process_main / monitor_main prototypes
│   └── logger.h
├── src/
│   ├── launcher.c        entry point: sets up IPC, forks everything, tears down
│   ├── mmu.c             translation, paging, LRU eviction, permissions
│   ├── process_sim.c     simulated workload generator
│   ├── monitor.c         periodic shared-memory stats reader
│   ├── ipc_common.c      ftok/shmget/semget/msgget + semaphore wrappers
│   └── logger.c          timestamped global logging
└── logs/                 vm_simulation.log written here at runtime
```
