CC      = gcc
CFLAGS  = -Wall -Wextra -std=gnu11 -Iinclude -g
TARGET  = vmsim

SRC = src/launcher.c \
      src/ipc_common.c \
      src/logger.c \
      src/mmu.c \
      src/process_sim.c \
      src/monitor.c

OBJ = $(SRC:.c=.o)

.PHONY: all run clean ipc-clean

all: $(TARGET)

$(TARGET): $(OBJ)
	$(CC) $(CFLAGS) -o $@ $(OBJ)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

# Usage: make run ARGS="6 60"
run: all
	./$(TARGET) $(ARGS)

clean:
	rm -f $(OBJ) $(TARGET)
	rm -f logs/*.log

# Removes stale SysV IPC resources left behind by a crashed/killed run.
ipc-clean:
	@echo "Removing stale SysV IPC (shm/sem/msg) owned by $$(whoami)..."
	@ipcs -m | awk -v u=$$(whoami) '$$3==u{print $$2}' | xargs -r -n1 ipcrm -m 2>/dev/null; true
	@ipcs -s | awk -v u=$$(whoami) '$$3==u{print $$2}' | xargs -r -n1 ipcrm -s 2>/dev/null; true
	@ipcs -q | awk -v u=$$(whoami) '$$3==u{print $$2}' | xargs -r -n1 ipcrm -q 2>/dev/null; true
