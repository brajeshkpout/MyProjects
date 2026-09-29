import json

import pytest

from graphnexus.cli import main
from graphnexus.graph import write_edge_list


@pytest.fixture
def edge_file(tmp_path):
    f = tmp_path / "edges.txt"
    write_edge_list(f, [(1, 2), (2, 3), (3, 1), (3, 4), (4, 5), (5, 6), (6, 4), (10, 11), (1, 1), (2, 1)], "test")
    return f


@pytest.fixture
def db(tmp_path, edge_file, capsys):
    out = tmp_path / "g.gnx"
    assert main(["import", str(edge_file), str(out)]) == 0
    capsys.readouterr()
    return str(out)


def test_import_reports_stats(tmp_path, edge_file, capsys):
    out = tmp_path / "x.gnx"
    assert main(["import", str(edge_file), str(out)]) == 0
    text = capsys.readouterr().out
    assert "nodes     : 8" in text and "edges     : 8" in text
    assert "1 self-loops, 1 duplicate" in text and out.exists()


def test_import_directed_flag(tmp_path, edge_file, capsys):
    out = tmp_path / "d.gnx"
    assert main(["import", str(edge_file), str(out), "--directed"]) == 0
    assert "directed" in capsys.readouterr().out
    assert main(["info", str(out)]) == 0
    assert "directed" in capsys.readouterr().out


def test_info_verify(db, capsys):
    assert main(["info", db, "--verify"]) == 0
    assert "Checksum    : OK" in capsys.readouterr().out


def test_node_and_edge_commands(db, capsys):
    assert main(["node", db, "3"]) == 0
    out = capsys.readouterr().out
    assert "degree    : 3" in out and "1, 2, 4" in out
    assert main(["edge", db, "3", "4"]) == 0
    assert "EXISTS" in capsys.readouterr().out
    assert main(["edge", db, "1", "6"]) == 2
    assert "does not exist" in capsys.readouterr().out


def test_unknown_node_is_a_clean_error(db, capsys):
    assert main(["node", db, "999"]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_traversals_and_path(db, capsys):
    assert main(["bfs", db, "1"]) == 0
    assert "reached 6 of 8 nodes" in capsys.readouterr().out
    assert main(["dfs", db, "1"]) == 0
    assert "Pre-order: 1, 2, 3, 4, 5, 6" in capsys.readouterr().out
    assert main(["path", db, "1", "6"]) == 0
    assert "3 hops" in capsys.readouterr().out
    assert main(["path", db, "1", "10"]) == 2
    assert "No path" in capsys.readouterr().out


def test_pagerank_and_components(db, capsys):
    assert main(["pagerank", db, "--top", "3"]) == 0
    out = capsys.readouterr().out
    assert "converged" in out and out.count("\n") >= 6
    assert main(["components", db]) == 0
    out = capsys.readouterr().out
    assert "WCC" in out and "SCC" in out and "largest size: 6 nodes" in out


def test_analyze_text_and_json(db, capsys):
    assert main(["analyze", db, "--top", "2"]) == 0
    text = capsys.readouterr().out
    assert "Top 2 nodes by PageRank" in text and "largest size: 6 nodes" in text
    assert main(["analyze", db, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["nodes"] == 8 and data["wcc"]["largest_size"] == 6
    assert len(data["top_pagerank"]) == 8  # --top defaults to 10 but the graph only has 8 nodes
    assert data["scc"]["count"] == 2


def test_benchmark_command(db, capsys):
    assert main(["benchmark", db, "--queries", "50", "--traversals", "3", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    names = {t["name"] for t in data["timings"]}
    assert "node lookup (hit)" in names and all(t["mean_ns"] > 0 for t in data["timings"])
    assert main(["benchmark", db, "--queries", "20", "--traversals", "2"]) == 0
    assert "operation" in capsys.readouterr().out


def test_generate_then_import(tmp_path, capsys):
    txt = tmp_path / "s.txt"
    assert main(["generate", str(txt), "--nodes", "200", "--attach", "4"]) == 0
    assert main(["import", str(txt), str(tmp_path / "s.gnx")]) == 0
    assert "nodes     : 200" in capsys.readouterr().out


def test_error_paths(tmp_path, capsys):
    assert main(["info", str(tmp_path / "nope.gnx")]) == 1
    assert "Error:" in capsys.readouterr().err
    bad = tmp_path / "bad.txt"
    bad.write_text("1 2\nfoo bar\n")
    assert main(["import", str(bad), str(tmp_path / "o.gnx")]) == 1
    assert "node ids must be integers" in capsys.readouterr().err
    assert main(["import", str(tmp_path / "missing.txt"), str(tmp_path / "o.gnx")]) == 1
    capsys.readouterr()
    with pytest.raises(SystemExit):
        main([])
