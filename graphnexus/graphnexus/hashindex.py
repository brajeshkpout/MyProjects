"""Custom open-addressing hash indexes, serialised as flat arrays inside the binary file.

Two indexes are used by the storage engine:

* **Node index**  - maps an external node id (signed 64-bit int) -> dense node index (uint32).
  Slot layout: ``<qI`` (12 bytes). An empty slot has ``value == 0xFFFFFFFF``.
* **Edge index**  - a hash *set* of directed edges. The key is ``(src << 32) | dst`` using dense
  node indexes. Slot layout: ``<Q`` (8 bytes). An empty slot is ``0xFFFFFFFFFFFFFFFF``.

Both use linear probing over a power-of-two table with load factor <= 0.5, and the
SplitMix64 finaliser as hash function. Because the tables are stored in the file, a lookup
is a couple of ``mmap`` reads: no index has to be rebuilt when the database is opened.
"""
from __future__ import annotations

import struct
from typing import Iterable, Optional, Sequence, Tuple

MASK64 = (1 << 64) - 1

NODE_SLOT = struct.Struct("<qI")
NODE_EMPTY = 0xFFFFFFFF
EDGE_SLOT = struct.Struct("<Q")
EDGE_EMPTY = MASK64

MAX_NODES = NODE_EMPTY - 1  # dense indexes must stay below the empty sentinel


def hash64(key: int) -> int:
    """SplitMix64 finaliser: a fast, well-distributed 64-bit integer mixer."""
    x = ((key & MASK64) + 0x9E3779B97F4A7C15) & MASK64
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & MASK64
    return x ^ (x >> 31)


def capacity_for(count: int) -> int:
    """Smallest power of two (>= 8) keeping the load factor at or below 0.5."""
    cap = 8
    while cap < count * 2:
        cap <<= 1
    return cap


def edge_key(src: int, dst: int) -> int:
    return (src << 32) | dst


# --------------------------------------------------------------------------- node index
def build_node_index(ext_ids: Sequence[int]) -> Tuple[bytes, int]:
    """Build the serialised node index for ``ext_ids`` (position in the sequence = dense index).

    Returns ``(blob, capacity)``. Raises ``ValueError`` on duplicate ids.
    """
    n = len(ext_ids)
    if n > MAX_NODES:
        raise ValueError(f"Too many nodes ({n}); the maximum is {MAX_NODES}")
    cap = capacity_for(n)
    mask = cap - 1
    keys = [0] * cap
    vals = [NODE_EMPTY] * cap
    for idx, ext in enumerate(ext_ids):
        slot = hash64(ext) & mask
        while vals[slot] != NODE_EMPTY:
            if keys[slot] == ext:
                raise ValueError(f"Duplicate node id {ext}")
            slot = (slot + 1) & mask
        keys[slot] = ext
        vals[slot] = idx
    flat = [x for pair in zip(keys, vals) for x in pair]
    return struct.pack("<" + "qI" * cap, *flat), cap


def lookup_node(buf, offset: int, capacity: int, ext_id: int) -> Optional[int]:
    """Return the dense index of ``ext_id`` or ``None``. ``buf`` is bytes / mmap."""
    if not -(1 << 63) <= ext_id < (1 << 63):
        return None
    mask = capacity - 1
    slot = hash64(ext_id) & mask
    unpack = NODE_SLOT.unpack_from
    size = NODE_SLOT.size
    while True:
        key, val = unpack(buf, offset + slot * size)
        if val == NODE_EMPTY:
            return None
        if key == ext_id:
            return val
        slot = (slot + 1) & mask


# --------------------------------------------------------------------------- edge index
def build_edge_index(pairs: Iterable[Tuple[int, int]], count: int) -> Tuple[bytes, int]:
    """Build the serialised edge hash-set from directed ``(src_idx, dst_idx)`` pairs."""
    cap = capacity_for(count)
    mask = cap - 1
    table = [EDGE_EMPTY] * cap
    for src, dst in pairs:
        key = edge_key(src, dst)
        slot = hash64(key) & mask
        while table[slot] != EDGE_EMPTY:
            if table[slot] == key:
                break  # already present
            slot = (slot + 1) & mask
        else:
            table[slot] = key
    return struct.pack(f"<{cap}Q", *table), cap


def lookup_edge(buf, offset: int, capacity: int, src: int, dst: int) -> bool:
    """True if the directed edge ``src -> dst`` (dense indexes) is in the index."""
    key = edge_key(src, dst)
    mask = capacity - 1
    slot = hash64(key) & mask
    unpack = EDGE_SLOT.unpack_from
    while True:
        (stored,) = unpack(buf, offset + slot * 8)
        if stored == EDGE_EMPTY:
            return False
        if stored == key:
            return True
        slot = (slot + 1) & mask
