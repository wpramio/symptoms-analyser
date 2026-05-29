import pytest
from symptoms_analyser.utils import split_into_chunks, merge_chunks

def test_split_into_chunks_empty():
    assert split_into_chunks("") == []
    assert split_into_chunks("   \n   ") == []

def test_split_into_chunks_no_timestamps():
    text = "Hello world\nThis is a transcript\nwithout any timestamps."
    expected = [
        {
            "timestamp": "00:00:00",
            "text": "Hello world\nThis is a transcript\nwithout any timestamps."
        }
    ]
    assert split_into_chunks(text) == expected

def test_split_into_chunks_with_timestamps():
    text = """
Some initial header info
00:01:10
Terapeuta: Olá, como vai?
Paciente: Tudo bem.
00:02:15
Terapeuta: O que te traz aqui hoje?
"""
    expected = [
        {
            "timestamp": "00:00:00",
            "text": "Some initial header info"
        },
        {
            "timestamp": "00:01:10",
            "text": "Terapeuta: Olá, como vai?\nPaciente: Tudo bem."
        },
        {
            "timestamp": "00:02:15",
            "text": "Terapeuta: O que te traz aqui hoje?"
        }
    ]
    assert split_into_chunks(text) == expected

def test_merge_chunks_blocks_per_call_one_or_less():
    chunks = [
        {"timestamp": "00:01:00", "text": "Hello"},
        {"timestamp": "00:02:00", "text": "World"}
    ]
    assert merge_chunks(chunks, 1) == chunks
    assert merge_chunks(chunks, 0) == chunks
    assert merge_chunks(chunks, -5) == chunks

def test_merge_chunks_batching():
    chunks = [
        {"timestamp": "00:01:00", "text": "Block 1"},
        {"timestamp": "00:02:00", "text": "Block 2"},
        {"timestamp": "00:03:00", "text": "Block 3"},
        {"timestamp": "00:04:00", "text": "Block 4"},
        {"timestamp": "00:05:00", "text": "Block 5"},
    ]
    
    # Batch size 2
    merged = merge_chunks(chunks, 2)
    assert len(merged) == 3
    
    assert merged[0] == {
        "timestamp": "00:01:00",
        "text": "00:01:00\nBlock 1\n\n00:02:00\nBlock 2"
    }
    assert merged[1] == {
        "timestamp": "00:03:00",
        "text": "00:03:00\nBlock 3\n\n00:04:00\nBlock 4"
    }
    assert merged[2] == {
        "timestamp": "00:05:00",
        "text": "00:05:00\nBlock 5"
    }
