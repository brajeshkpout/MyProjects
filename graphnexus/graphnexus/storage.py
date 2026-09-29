"""GraphNexus binary file format (``.gnx``) - writer and memory-mapped reader.

All integers are little-endian. See ``docs/FORMAT.md`` for the full specification.

    [ header (fixed size) ]
    [ external ids   : n      x int64  ]   sorted ascending; position = dense index
    [ out offsets    : n + 1  x uint64 ]   CSR row pointers into the out-adjacency array
    [ out adjacency  : A      x uint32 ]   sorted dense indexes of out-neighbours
    [ in  offsets    : n + 1  x uint64 ]   only for directed graphs (otherwise in == out)
    [ in  adjacency  : A      x uint32 ]   only for directed graphs
    [ node hash index: cap    x (int64, uint32) ]
    [ edge hash index: cap    x uint64 ]
"""
from __future__ import annotations

import mmap
import os
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .graph import Graph
from .hashindex import build_edge_index, build_node_index, lookup_edge, lookup_node

MAGIC = b"GNX1"
VERSION = 1
FLAG_DIRECTED = 1

# magic, version, flags, num_nodes | num_edges, off_ext_ids, off_out_offsets, off_out_adj,
# off_in_offsets, off_in_adj, off_node_index, cap_node_index, off_edge_index, cap_edge_index | crc32
HEADER = struct.Struct("<4sHHI" + "Q" * 10 + "I")
HEADER_SIZE = HEADER.size


class StorageError(Exception):
    """The file is not a valid / intact GraphNexus database."""


@dataclass(frozen=True)
class WriteSummary:
    path: Path
    size_bytes: int
    num_nodes: int
    num_edges: int
    directed: bool
    node_index_capacity: int
    edge_index_capacity: int


def _csr(adj: Sequence[Sequence[int]]) -> Tuple[bytes, bytes]:
    offsets: List[int] = [0]
    flat: List[int] = []
    for row in adj:
        flat.extend(row)
        offsets.append(len(flat))
    return struct.pack(f"<{len(offsets)}Q", *offsets), struct.pack(f"<{len(flat)}I", *flat)


def write_store(path, graph: Graph) -> WriteSummary:
    """Serialise ``graph`` to ``path`` (written atomically via a temporary file)."""
    path = Path(path)
    n = graph.n
    ext_blob = struct.pack(f"<{n}q", *graph.ext_ids)
    out_off, out_adj = _csr([graph.out_neighbors(i) for i in range(n)])
    node_blob, node_cap = build_node_index(graph.ext_ids)
    entries = len(out_adj) // 4
    edge_pairs = ((u, v) for u in range(n) for v in graph.out_neighbors(u))
    edge_blob, edge_cap = build_edge_index(edge_pairs, entries)

    sections: List[bytes] = [ext_blob, out_off, out_adj]
    pos = HEADER_SIZE
    off_ext = pos
    pos += len(ext_blob)
    off_out_off = pos
    pos += len(out_off)
    off_out_adj = pos
    pos += len(out_adj)
    if graph.directed:
        in_off, in_adj = _csr([graph.in_neighbors(i) for i in range(n)])
        off_in_off = pos
        pos += len(in_off)
        off_in_adj = pos
        pos += len(in_adj)
        sections += [in_off, in_adj]
    else:  # undirected: in == out, share the same sections
        off_in_off, off_in_adj = off_out_off, off_out_adj
    off_node_idx = pos
    pos += len(node_blob)
    off_edge_idx = pos
    pos += len(edge_blob)
    sections += [node_blob, edge_blob]

    crc = 0
    for blob in sections:
        crc = zlib.crc32(blob, crc)

    header = HEADER.pack(
        MAGIC, VERSION, FLAG_DIRECTED if graph.directed else 0, n,
        graph.num_edges, off_ext, off_out_off, off_out_adj, off_in_off, off_in_adj,
        off_node_idx, node_cap, off_edge_idx, edge_cap, crc & 0xFFFFFFFF,
    )

    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(header)
            for blob in sections:
                fh.write(blob)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return WriteSummary(path, pos, n, graph.num_edges, graph.directed, node_cap, edge_cap)


class GraphStore:
    """Read-only, memory-mapped view of a ``.gnx`` file.

    Implements the same ``GraphView`` protocol as :class:`~graphnexus.graph.Graph`
    (``n``, ``out_neighbors``, ``in_neighbors``) so all algorithms run directly on disk data.
    Node and edge lookups go through the on-disk hash indexes.
    """

    def __init__(self, path) -> None:
        self.path = Path(path)
        try:
            self._fh = open(self.path, "rb")
        except OSError as exc:
            raise StorageError(f"Cannot open {self.path}: {exc.strerror or exc}") from exc
        try:
            size = os.fstat(self._fh.fileno()).st_size
            if size < HEADER_SIZE:
                raise StorageError(f"{self.path} is too small to be a GraphNexus database")
            self._mm = mmap.mmap(self._fh.fileno(), 0, access=mmap.ACCESS_READ)
            self._parse_header(size)
        except BaseException:
            self.close()
            raise

    # ------------------------------------------------------------------ header handling
    def _parse_header(self, size: int) -> None:
        (magic, version, flags, n, m, self._off_ext, self._off_out_off, self._off_out_adj,
         self._off_in_off, self._off_in_adj, self._off_node_idx, self._cap_node,
         self._off_edge_idx, self._cap_edge, self._crc) = HEADER.unpack_from(self._mm, 0)
        if magic != MAGIC:
            raise StorageError(f"{self.path} is not a GraphNexus file (bad magic number)")
        if version != VERSION:
            raise StorageError(f"Unsupported GraphNexus format version {version}")
        for cap in (self._cap_node, self._cap_edge):
            if cap < 8 or cap & (cap - 1):
                raise StorageError("Corrupt header: hash index capacity is not a power of two")
        expected = self._off_edge_idx + self._cap_edge * 8
        if expected != size:
            raise StorageError(
                f"File size mismatch (expected {expected} bytes, found {size}); the file is truncated or corrupt"
            )
        self._n = n
        self._num_edges = m
        self.directed = bool(flags & FLAG_DIRECTED)

    def verify(self) -> bool:
        """Recompute the body CRC-32 and compare it with the header. Returns True if intact."""
        crc = 0
        view = memoryview(self._mm)
        try:
            chunk = 1 << 20
            for start in range(HEADER_SIZE, len(self._mm), chunk):
                crc = zlib.crc32(view[start:start + chunk], crc)
        finally:
            view.release()
        return (crc & 0xFFFFFFFF) == self._crc

    # ------------------------------------------------------------------------ properties
    @property
    def n(self) -> int:
        return self._n

    @property
    def num_nodes(self) -> int:
        return self._n

    @property
    def num_edges(self) -> int:
        return self._num_edges

    @property
    def file_size(self) -> int:
        return len(self._mm)

    # --------------------------------------------------------------- node / edge lookups
    def node_index(self, ext_id: int) -> Optional[int]:
        """Hash-index lookup: external id -> dense index (``None`` if absent)."""
        return lookup_node(self._mm, self._off_node_idx, self._cap_node, ext_id)

    def has_node(self, ext_id: int) -> bool:
        return self.node_index(ext_id) is not None

    def external_id(self, idx: int) -> int:
        self._check(idx)
        return struct.unpack_from("<q", self._mm, self._off_ext + idx * 8)[0]

    def has_edge(self, u_ext: int, v_ext: int) -> bool:
        """Hash-index lookup of the edge ``u -> v`` (either direction for undirected graphs)."""
        u, v = self.node_index(u_ext), self.node_index(v_ext)
        if u is None or v is None:
            return False
        return lookup_edge(self._mm, self._off_edge_idx, self._cap_edge, u, v)

    # -------------------------------------------------------------------- adjacency reads
    def _row(self, offsets_off: int, adj_off: int, idx: int) -> Sequence[int]:
        self._check(idx)
        start, end = struct.unpack_from("<QQ", self._mm, offsets_off + idx * 8)
        deg = end - start
        if deg == 0:
            return ()
        return struct.unpack_from(f"<{deg}I", self._mm, adj_off + start * 4)

    def out_neighbors(self, idx: int) -> Sequence[int]:
        return self._row(self._off_out_off, self._off_out_adj, idx)

    def in_neighbors(self, idx: int) -> Sequence[int]:
        return self._row(self._off_in_off, self._off_in_adj, idx)

    def out_degree(self, idx: int) -> int:
        self._check(idx)
        start, end = struct.unpack_from("<QQ", self._mm, self._off_out_off + idx * 8)
        return end - start

    def in_degree(self, idx: int) -> int:
        self._check(idx)
        start, end = struct.unpack_from("<QQ", self._mm, self._off_in_off + idx * 8)
        return end - start

    def neighbors_of(self, ext_id: int, direction: str = "out") -> List[int]:
        """External ids of the neighbours of ``ext_id`` (``direction``: out / in)."""
        idx = self.node_index(ext_id)
        if idx is None:
            raise KeyError(ext_id)
        rows = self.out_neighbors(idx) if direction == "out" else self.in_neighbors(idx)
        return [self.external_id(j) for j in rows]

    def _check(self, idx: int) -> None:
        if not 0 <= idx < self._n:
            raise IndexError(f"node index {idx} out of range (0..{self._n - 1})")

    # ------------------------------------------------------------------------ lifecycle
    def close(self) -> None:
        mm = getattr(self, "_mm", None)
        if mm is not None and not mm.closed:
            mm.close()
        fh = getattr(self, "_fh", None)
        if fh is not None and not fh.closed:
            fh.close()

    def __enter__(self) -> "GraphStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
