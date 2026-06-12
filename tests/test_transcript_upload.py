import pytest
from pathlib import Path
from unittest import mock
from symptoms_analyser.controllers.transcript_upload import (
    allowed_file,
    handle_transcript_upload,
    tasks
)

def test_allowed_file():
    assert allowed_file("test.txt") is True
    assert allowed_file("test.docx") is True
    assert allowed_file("test.pdf") is False

def test_handle_transcript_upload_invalid_ext():
    file_mock = mock.Mock()
    with pytest.raises(ValueError, match="Extensão de arquivo não permitida"):
        handle_transcript_upload(file_mock, "invalid.pdf", 1)

@mock.patch("symptoms_analyser.controllers.transcript_upload.threading.Thread")
def test_handle_transcript_upload_valid(mock_thread):
    file_mock = mock.Mock()
    
    # Mock UPLOAD_FOLDER path
    fake_folder = Path("/tmp/fake_uploads")
    
    with mock.patch("symptoms_analyser.controllers.transcript_upload.UPLOAD_FOLDER", fake_folder):
        task_id = handle_transcript_upload(
            file_stream=file_mock,
            filename="valid.txt",
            therapy_session_id=1,
            skip_extension_check=False
        )
        
    assert task_id in tasks
    assert tasks[task_id]["status"] == "processing"
    
    # Ensure save was called on file stream
    file_mock.save.assert_called_once_with(fake_folder / "valid.txt")
    
    # Ensure background thread was initialized and started
    mock_thread.assert_called_once()
    mock_thread.return_value.start.assert_called_once()
