import gzip

import pytest

from graphnexus.graph import EdgeListError, Graph, load_graph, read_edge_list, write_edge_list


def test_from_edges_undirected_dedups_and_drops_self_loops():
    g = Graph.from_edges([(5, 1), (1, 5), (1, 5), (2, 2), (5, 9)], directed=False)
    assert g.ext_ids == [1, 2, 5, 9]  # sorted; self-loop node 2 still exists
    assert g.num_edges == 2 and g.self_loops_dropped == 1 and g.duplicates_dropped == 2
    assert list(g.out_neighbors(2)) == [0, 3]  # node 5 -> neighbours 1 and 9
    assert list(g.in_neighbors(2)) == list(g.out_neighbors(2))


def test_from_edges_directed_keeps_direction():
    g = Graph.from_edges([(1, 2), (2, 1), (1, 3)], directed=True)
    assert g.num_edges == 3
    assert list(g.out_neighbors(0)) == [1, 2]
    assert list(g.in_neighbors(0)) == [1]


def test_extra_isolated_nodes():
    g = Graph.from_edges([(1, 2)], nodes=[99])
    assert g.n == 3 and list(g.out_neighbors(2)) == []


def test_read_edge_list_formats(tmp_path):
    f = tmp_path / "e.txt"
    f.write_text("# comment\n% other\n\n1 2\n3\t4\n5,6\n7 8 0.5\n")
    assert list(read_edge_list(f)) == [(1, 2), (3, 4), (5, 6), (7, 8)]


def test_read_edge_list_gzip(tmp_path):
    f = tmp_path / "e.txt.gz"
    with gzip.open(f, "wt") as fh:
        fh.write("# hi\n10 20\n20 30\n")
    assert load_graph(f).num_edges == 2


@pytest.mark.parametrize("content", ["1\n", "a b\n", "1 x\n"])
def test_malformed_lines_report_line_number(tmp_path, content):
    f = tmp_path / "bad.txt"
    f.write_text("1 2\n" + content)
    with pytest.raises(EdgeListError, match=r":2:"):
        list(read_edge_list(f))


def test_empty_edge_list_rejected(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("# nothing here\n")
    with pytest.raises(EdgeListError):
        load_graph(f)


def test_write_then_read_roundtrip(tmp_path):
    f = tmp_path / "out.txt"
    write_edge_list(f, [(1, 2), (2, 3)], header="my graph")
    assert f.read_text().startswith("# my graph")
    assert list(read_edge_list(f)) == [(1, 2), (2, 3)]
