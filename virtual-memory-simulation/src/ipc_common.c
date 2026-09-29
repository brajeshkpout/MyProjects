#include "ipc_common.h"

#include <stdio.h>
#include <stdlib.h>
#include <errno.h>

key_t make_key(char proj_id) {
    key_t k = ftok(IPC_KEY_PATH, proj_id);
    if (k == -1) {
        perror("ftok");
        exit(1);
    }
    return k;
}

int get_shm_segment(int create) {
    key_t k = make_key(IPC_PROJ_SHM);
    int flags = 0666 | (create ? IPC_CREAT : 0);
    int id = shmget(k, sizeof(shared_state_t), flags);
    if (id == -1) {
        perror("shmget");
        exit(1);
    }
    return id;
}

int get_sem_set(int create) {
    key_t k = make_key(IPC_PROJ_SEM);
    int flags = 0666 | (create ? IPC_CREAT : 0);
    int id = semget(k, SEM_COUNT, flags);
    if (id == -1) {
        perror("semget");
        exit(1);
    }
    return id;
}

int get_req_queue(int create) {
    key_t k = make_key(IPC_PROJ_REQ_Q);
    int flags = 0666 | (create ? IPC_CREAT : 0);
    int id = msgget(k, flags);
    if (id == -1) {
        perror("msgget (request queue)");
        exit(1);
    }
    return id;
}

int get_resp_queue(int create) {
    key_t k = make_key(IPC_PROJ_RESP_Q);
    int flags = 0666 | (create ? IPC_CREAT : 0);
    int id = msgget(k, flags);
    if (id == -1) {
        perror("msgget (response queue)");
        exit(1);
    }
    return id;
}

static void sem_op(int semid, int idx, int val) {
    struct sembuf sb;
    sb.sem_num = idx;
    sb.sem_op = val;
    sb.sem_flg = 0;
    while (semop(semid, &sb, 1) == -1) {
        if (errno == EINTR) continue;
        perror("semop");
        exit(1);
    }
}

void sem_lock(int semid, int idx)   { sem_op(semid, idx, -1); }
void sem_unlock(int semid, int idx) { sem_op(semid, idx, 1);  }
void sem_wait_n(int semid, int idx) { sem_op(semid, idx, -1); }
void sem_post_n(int semid, int idx) { sem_op(semid, idx, 1);  }
