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
