import random

import pytest

from graphnexus.hashindex import (
    NODE_SLOT, build_edge_index, build_node_index, capacity_for, hash64, lookup_edge, lookup_node,
)


def test_capacity_is_power_of_two_with_low_load():
    for count in (0, 1, 3, 4, 5, 100, 4039, 100_000):
        cap = capacity_for(count)
        assert cap & (cap - 1) == 0 and cap >= 8 and cap >= count * 2


def test_hash64_is_deterministic_and_spreads_sequential_keys():
    assert hash64(12345) == hash64(12345)
    buckets = {hash64(i) & 1023 for i in range(2000)}
    assert len(buckets) > 800  # sequential ids do not cluster


def test_node_index_roundtrip_including_negative_and_large_ids():
    ids = sorted({-(2**63), -5, -1, 0, 1, 7, 42, 2**40, 2**63 - 1})
    blob, cap = build_node_index(ids)
    assert len(blob) == cap * NODE_SLOT.size
    for idx, ext in enumerate(ids):
        assert lookup_node(blob, 0, cap, ext) == idx
    for missing in (2, 8, -2, 2**41, 2**64):
        assert lookup_node(blob, 0, cap, missing) is None


def test_node_index_handles_heavy_collisions():
    ids = [i * 4096 for i in range(500)]  # many share low bits before mixing
    blob, cap = build_node_index(ids)
    assert all(lookup_node(blob, 0, cap, e) == i for i, e in enumerate(ids))


def test_node_index_lookup_with_offset_prefix():
    ids = [3, 9, 27]
    blob, cap = build_node_index(ids)
    padded = b"\xff" * 17 + blob
    assert [lookup_node(padded, 17, cap, e) for e in ids] == [0, 1, 2]


def test_node_index_rejects_duplicates():
    with pytest.raises(ValueError):
        build_node_index([1, 2, 2])


def test_edge_index_membership():
    rng = random.Random(1)
    pairs = {(rng.randrange(300), rng.randrange(300)) for _ in range(2000)}
    blob, cap = build_edge_index(pairs, len(pairs))
    assert all(lookup_edge(blob, 0, cap, a, b) for a, b in pairs)
    absent = [(a, b) for a in range(300) for b in range(300) if (a, b) not in pairs][:3000]
    assert not any(lookup_edge(blob, 0, cap, a, b) for a, b in absent)


def test_edge_index_is_directional_and_dedups():
    blob, cap = build_edge_index([(1, 2), (1, 2)], 2)
    assert lookup_edge(blob, 0, cap, 1, 2) and not lookup_edge(blob, 0, cap, 2, 1)
