import json
import logging

from src.main_node import JSONFormatter


def test_json_formatter():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        "test", logging.INFO, "test.py", 1, "test message", None, None
    )
    formatted = formatter.format(record)
    parsed = json.loads(formatted)
    assert parsed["message"] == "test message"
    assert parsed["level"] == "INFO"
    assert parsed["name"] == "test"
    assert "timestamp" in parsed


def test_json_formatter_with_exception():
    formatter = JSONFormatter()
    try:
        _ = 1 / 0
    except ZeroDivisionError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        "test", logging.ERROR, "test.py", 1, "error message", None, exc_info
    )
    formatted = formatter.format(record)
    parsed = json.loads(formatted)
    assert parsed["message"] == "error message"
    assert parsed["level"] == "ERROR"
    assert "ZeroDivisionError" in parsed["exc_info"]
