import pytest

from graphnexus.datasets import DatasetError, SNAP_DATASETS, download_dataset, generate_social_graph
from graphnexus.graph import Graph


def test_generator_is_deterministic_and_simple():
    a = generate_social_graph(300, 5, seed=7)
    assert a == generate_social_graph(300, 5, seed=7)
    assert a != generate_social_graph(300, 5, seed=8)
    assert len(set(a)) == len(a) and all(u < v for u, v in a)  # no dupes / self-loops


def test_generator_default_matches_ego_facebook_scale():
    edges = generate_social_graph()
    g = Graph.from_edges(edges)
    assert g.n == 4039
    assert 80_000 < g.num_edges < 95_000


def test_generator_validation():
    with pytest.raises(DatasetError):
        generate_social_graph(5, 10)
    with pytest.raises(DatasetError):
        generate_social_graph(100, 3, triad_prob=2)


def test_download_unknown_dataset(tmp_path):
    with pytest.raises(DatasetError):
        download_dataset("nope", tmp_path)


def test_download_failure_is_reported(tmp_path, monkeypatch):
    import urllib.error
    import urllib.request

    def boom(*a, **k):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(DatasetError, match="Download failed"):
        download_dataset("facebook", tmp_path)
    assert not list(tmp_path.iterdir())  # no partial files left behind


def test_registry_has_facebook_undirected():
    assert "snap.stanford.edu" in SNAP_DATASETS["facebook"].url and not SNAP_DATASETS["facebook"].directed
