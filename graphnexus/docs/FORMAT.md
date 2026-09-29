# GraphNexus binary format (`.gnx`, version 1)

All integers are **little-endian**. A file is a fixed-size header followed by sections stored back to back.
Sections are located through offsets in the header, so readers never scan the file.

## Header (96 bytes)

| Field | Type | Meaning |
|---|---|---|
| magic | 4 bytes | `GNX1` |
| version | uint16 | format version (currently `1`) |
| flags | uint16 | bit 0 = directed |
| num_nodes | uint32 | number of nodes `n` |
| num_edges | uint64 | logical edges (undirected edges count once) |
| off_ext_ids | uint64 | byte offset of the external-id array |
| off_out_offsets | uint64 | byte offset of the out-adjacency row pointers |
| off_out_adj | uint64 | byte offset of the out-adjacency array |
| off_in_offsets | uint64 | byte offset of the in-adjacency row pointers (equals `off_out_offsets` if undirected) |
| off_in_adj | uint64 | byte offset of the in-adjacency array (equals `off_out_adj` if undirected) |
| off_node_index | uint64 | byte offset of the node hash index |
| cap_node_index | uint64 | slots in the node hash index (power of two) |
| off_edge_index | uint64 | byte offset of the edge hash index |
| cap_edge_index | uint64 | slots in the edge hash index (power of two) |
| crc32 | uint32 | CRC-32 of every byte after the header |

## Sections

| Section | Layout |
|---|---|
| external ids | `n` x int64, sorted ascending. Position in this array is the node's **dense index** |
| out offsets | `n + 1` x uint64, CSR row pointers (counted in entries, not bytes) |
| out adjacency | `A` x uint32, dense indexes of out-neighbours, sorted per node |
| in offsets / in adjacency | same layout; **only present for directed graphs** |
| node hash index | `cap` slots of `(int64 external_id, uint32 dense_index)`; empty slot = `dense_index 0xFFFFFFFF` |
| edge hash index | `cap` slots of `uint64 key = (src_dense << 32) \| dst_dense`; empty slot = `0xFFFFFFFFFFFFFFFF` |

`A` is the number of stored adjacency entries: `num_edges` for directed graphs, `2 * num_edges` for undirected ones
(every undirected edge is stored in both directions). Self-loops and duplicate edges are removed on import.

## Hash indexes

* Hash function: the SplitMix64 finaliser applied to the 64-bit key (two's complement for negative ids).
* Table size: power of two, at least `2 x entries` (load factor <= 0.5), so every probe sequence ends at an empty slot.
* Collision resolution: linear probing (`slot = (slot + 1) & (cap - 1)`).

## Lookup cost

* `node(ext_id)`: hash, then usually 1-2 slot reads from the memory-mapped file.
* `edge(u, v)`: two node lookups plus one edge-index probe (no adjacency scan).
* `neighbours(idx)`: two row-pointer reads and one contiguous adjacency read.

## Integrity checks on open

The reader verifies the magic number, version, that both capacities are powers of two, and that
`off_edge_index + cap_edge_index * 8` equals the file size (detects truncation). `graphnexus info --verify`
additionally recomputes the CRC-32 (detects bit rot).
