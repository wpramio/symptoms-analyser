import pytest
from symptoms_analyser.controllers.therapy_sessions import allowed_file

def test_allowed_file_valid_extensions():
    # Test valid text extensions
    assert allowed_file("session1.txt") is True
    assert allowed_file("session2.docx") is True
    assert allowed_file("UPPERCASE.DOCX") is True
    assert allowed_file("UPPERCASE.TXT") is True

def test_allowed_file_invalid_extensions():
    # Test invalid extensions
    assert allowed_file("session1.pdf") is False
    assert allowed_file("session2.mp3") is False
    assert allowed_file("no_extension") is False
    assert allowed_file("invalid.txt.exe") is False

def test_allowed_file_empty_filename():
    assert allowed_file("") is False
    assert allowed_file(".") is False

def test_get_tdpm_table_data():
    from symptoms_analyser.controllers.admin import get_tdpm_table_data
    data = get_tdpm_table_data()
    assert len(data) == 20
    
    # Check the structure of the first dimension
    first_dim = data[0]
    assert first_dim["key"] == "1"
    assert first_dim["name"] == "Desregulação do Apetite"
    assert first_dim["category_class"] == "physio"
    assert len(first_dim["dim_items"]) > 0
    
    # Check the structure of an item
    first_item = first_dim["dim_items"][0]
    assert first_item["key"].startswith("1.")
    assert "name" in first_item
    assert "detailed" in first_item


def test_compute_graph_data():
    from symptoms_analyser.controllers.therapy_groups import compute_graph_data

    # Test with normal edges, bridges, isolated patients, and subgroup detection
    # Paciente 1, 2, 3 form a cycle (subgroup). Paciente 3 -> Paciente 4 is a bridge.
    # Paciente 5 has no interactions at all (isolated).
    group_patients = ["Paciente 1", "Paciente 2", "Paciente 3", "Paciente 4", "Paciente 5"]
    raw_edges = [
        {"source": "Paciente 1", "target": "Paciente 2", "type": "apoio", "evidence": "E1", "session_name": "S1"},
        {"source": "Paciente 2", "target": "Paciente 3", "type": "validacao", "evidence": "E2", "session_name": "S1"},
        {"source": "Paciente 3", "target": "Paciente 1", "type": "confronto", "evidence": "E3", "session_name": "S1"},
        {"source": "Paciente 3", "target": "Paciente 4", "type": "apoio", "evidence": "E4", "session_name": "S2"}, # Bridge!
    ]

    res = compute_graph_data(raw_edges, group_patients)

    assert "nodes_ordered" in res
    assert "subgroups" in res
    assert "isolated" in res
    assert "node_meta" in res
    assert "aggregated_edges" in res

    # Paciente 5 has no interactions at all
    assert "Paciente 5" in res["isolated"]
    # Paciente 4 is connected via a bridge, so after bridge removal, it is also isolated
    assert "Paciente 4" in res["isolated"]
    
    # The subgroup should be Paciente 1, 2, 3
    assert res["subgroups"] == [["Paciente 1", "Paciente 2", "Paciente 3"]]

    # Node meta classifications
    assert res["node_meta"]["Paciente 1"]["type"] == "subgroup"
    assert res["node_meta"]["Paciente 4"]["type"] == "isolated"
    assert res["node_meta"]["Paciente 5"]["type"] == "isolated"

    # Aggregated edges check
    agg = res["aggregated_edges"]
    assert len(agg) == 4
    # Bridge detection check
    bridge_edges = [e for e in agg if e["is_bridge"]]
    assert len(bridge_edges) == 1
    assert bridge_edges[0]["source"] == "Paciente 3"
    assert bridge_edges[0]["target"] == "Paciente 4"


