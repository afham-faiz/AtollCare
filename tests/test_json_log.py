import json
import threading

from src.services.json_log import append_log, read_log


def test_log_is_a_valid_json_array(tmp_path):
    path = tmp_path / "logs" / "x.json"
    append_log(path, {"n": 1})
    append_log(path, {"n": 2})
    assert json.load(open(path, encoding="utf-8")) == [{"n": 1}, {"n": 2}]


def test_missing_or_corrupt_file_reads_empty(tmp_path):
    assert read_log(tmp_path / "nope.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert read_log(bad) == []


def test_concurrent_appends_do_not_lose_entries(tmp_path):
    path = tmp_path / "c.json"
    threads = [threading.Thread(target=append_log, args=(path, {"i": i})) for i in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(e["i"] for e in read_log(path)) == list(range(20))
