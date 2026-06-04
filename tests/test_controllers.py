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
