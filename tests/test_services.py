import pytest
from app.services.rag_service import add_to_rag, rag_qa

def test_rag():
    add_to_rag("test.txt", "Test content")
    assert "Test" in rag_qa("test")