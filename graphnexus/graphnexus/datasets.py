"""Datasets: download well-known Stanford SNAP graphs or generate a synthetic social network."""
from __future__ import annotations

import random
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, NamedTuple, Set

from .graph import Edge


class DatasetError(Exception):
    """A dataset could not be downloaded or generated."""


class SnapDataset(NamedTuple):
    url: str
    directed: bool
    description: str


SNAP_DATASETS: Dict[str, SnapDataset] = {
    "facebook": SnapDataset(
        "https://snap.stanford.edu/data/facebook_combined.txt.gz", False,
        "ego-Facebook social circles: 4,039 nodes, 88,234 undirected edges",
    ),
    "wiki-vote": SnapDataset(
        "https://snap.stanford.edu/data/wiki-Vote.txt.gz", True,
        "Wikipedia adminship votes: 7,115 nodes, 103,689 directed edges",
    ),
    "gnutella08": SnapDataset(
        "https://snap.stanford.edu/data/p2p-Gnutella08.txt.gz", True,
        "Gnutella P2P network (Aug 2002): 6,301 nodes, 20,777 directed edges",
    ),
}


def download_dataset(name: str, dest_dir) -> Path:
    """Download a SNAP dataset (``.txt.gz``) into ``dest_dir`` and return the file path."""
    if name not in SNAP_DATASETS:
        raise DatasetError(f"Unknown dataset {name!r}. Choose from: {', '.join(sorted(SNAP_DATASETS))}")
    info = SNAP_DATASETS[name]
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / info.url.rsplit("/", 1)[-1]
    tmp = target.with_name(target.name + ".part")
    request = urllib.request.Request(info.url, headers={"User-Agent": "graphnexus/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as resp, open(tmp, "wb") as out:
            shutil.copyfileobj(resp, out)
        tmp.replace(target)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        if tmp.exists():
            tmp.unlink()
        raise DatasetError(
            f"Download failed ({exc}). Download {info.url} manually and pass it to 'graphnexus import'."
        ) from exc
    return target


def generate_social_graph(n: int = 4039, m: int = 22, triad_prob: float = 0.6, seed: int = 42) -> List[Edge]:
    """Synthetic social network (Holme-Kim: preferential attachment + triadic closure).

    With the defaults it has roughly the size of SNAP's ego-Facebook graph
    (~4,000 nodes, ~88,000 edges) and a similar hub-and-cluster structure. Deterministic for a seed.
    """
    if m < 1 or n <= m + 1:
        raise DatasetError("Need m >= 1 and n > m + 1")
    if not 0.0 <= triad_prob <= 1.0:
        raise DatasetError("triad_prob must be between 0 and 1")
    rng = random.Random(seed)
    adj: List[Set[int]] = [set() for _ in range(n)]
    repeated: List[int] = []  # each node appears once per incident edge -> degree-proportional sampling
    edges: List[Edge] = []

    def add(u: int, v: int) -> None:
        adj[u].add(v)
        adj[v].add(u)
        repeated.extend((u, v))
        edges.append((min(u, v), max(u, v)))

    for i in range(m + 1):  # seed clique
        for j in range(i):
            add(i, j)

    for new in range(m + 1, n):
        targets: Set[int] = set()
        last = None
        while len(targets) < m:
            if last is not None and rng.random() < triad_prob:
                candidates = sorted(w for w in adj[last] if w not in targets)
                if candidates:
                    targets.add(rng.choice(candidates))
                    continue
            t = rng.choice(repeated)
            if t not in targets:
                targets.add(t)
                last = t
        for t in sorted(targets):
            add(new, t)
    edges.sort()
    return edges
