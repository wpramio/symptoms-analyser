import pytest
from symptoms_analyser.controllers.evaluations import align_evaluations

def test_align_evaluations_both_none():
    assert align_evaluations(None, None) == []

def test_align_evaluations_comparison():
    data1 = {
        "aggregated": {
            "patients": {
                "Paciente1": {
                    "dimensions": {
                        "1": {
                            "name": "Dimensão 1",
                            "dimension_sum": 4
                        },
                        "2": {
                            "name": "Dimensão 2",
                            "dimension_sum": 6
                        },
                        "3": {
                            "name": "Dimensão 3",
                            "dimension_sum": 5
                        }
                    },
                    "items": {
                        "1.1": {
                            "name": "Item 1.1",
                            "score": 4,
                            "evidence": ["00:01:00 Ev1"]
                        },
                        "2.1": {
                            "name": "Item 2.1",
                            "score": 3,
                            "evidence": []
                        },
                        "3.1": {
                            "name": "Item 3.1",
                            "score": 5,
                            "evidence": []
                        }
                    }
                }
            }
        }
    }
    
    data2 = {
        "aggregated": {
            "patients": {
                "Paciente1": {
                    "dimensions": {
                        "1": {
                            "name": "Dimensão 1",
                            "dimension_sum": 6  # symptom increased
                        },
                        "2": {
                            "name": "Dimensão 2",
                            "dimension_sum": 3  # symptom decreased
                        },
                        "3": {
                            "name": "Dimensão 3",
                            "dimension_sum": 5  # stable
                        }
                    },
                    "items": {
                        "1.1": {
                            "name": "Item 1.1",
                            "score": 6,
                            "evidence": ["00:02:00 Ev2"]
                        },
                        "2.1": {
                            "name": "Item 2.1",
                            "score": 2,
                            "evidence": []
                        },
                        "3.1": {
                            "name": "Item 3.1",
                            "score": 5,
                            "evidence": []
                        }
                    }
                }
            }
        }
    }
    
    aligned = align_evaluations(data1, data2)
    assert len(aligned) == 1
    assert aligned[0]["name"] == "Paciente1"
    
    dims = aligned[0]["dimensions"]
    assert len(dims) == 3
    
    # Sort or check order: dimensions should be sorted by key (1, 2, 3)
    # Check Dim 1 (Increased: 4 -> 6)
    assert dims[0]["key"] == "1"
    assert dims[0]["score1"] == 4
    assert dims[0]["score2"] == 6
    assert dims[0]["max_size"] == 8
    assert dims[0]["change_class"] == "increased"
    assert dims[0]["change_symbol"] == "▲"
    assert dims[0]["items1"][0]["score"] == 4
    assert dims[0]["items2"][0]["score"] == 6
    
    # Check Dim 2 (Decreased: 6 -> 3)
    assert dims[1]["key"] == "2"
    assert dims[1]["score1"] == 6
    assert dims[1]["score2"] == 3
    assert dims[1]["change_class"] == "decreased"
    assert dims[1]["change_symbol"] == "▼"
    
    # Check Dim 3 (Stable: 5 -> 5)
    assert dims[2]["key"] == "3"
    assert dims[2]["score1"] == 5
    assert dims[2]["score2"] == 5
    assert dims[2]["change_class"] == "stable"
    assert dims[2]["change_symbol"] == "●"

def test_align_evaluations_dimension_16():
    # Dimension 16 has max_size = 12, others have max_size = 8
    data1 = {
        "aggregated": {
            "patients": {
                "Paciente2": {
                    "dimensions": {
                        "16": {
                            "name": "Dimensão 16",
                            "dimension_sum": 6
                        }
                    },
                    "items": {}
                }
            }
        }
    }
    
    aligned = align_evaluations(data1, None)
    assert len(aligned) == 1
    dims = aligned[0]["dimensions"]
    assert len(dims) == 1
    assert dims[0]["key"] == "16"
    assert dims[0]["max_size"] == 12
    # sev1 = math.ceil((6 / 12) * 4) = 2
    assert dims[0]["sev1"] == 2
