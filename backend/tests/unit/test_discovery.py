import json
from datetime import date

from app.integrations.azure_storage.sources import LocalExportSource
from worker.ingestion.discovery import discover_runs


def _w(p, text=""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_v2_layout_with_manifest(tmp_path):
    base = tmp_path / "c" / "root" / "exp" / "20261001-20261031" / "run-1"
    _w(base / "part_0_0001.csv", "date,cost\n")
    _w(base / "manifest.json", json.dumps({
        "runInfo": {"submittedTime": "2026-11-02T06:00:00Z", "startDate": "2026-10-01T00:00:00", "endDate": "2026-10-31T00:00:00"},
        "blobs": [{"blobName": "root/exp/20261001-20261031/run-1/part_0_0001.csv", "dataRowCount": 0}],
    }))
    runs = discover_runs(LocalExportSource(str(tmp_path)), "c", "root/exp/")
    assert len(runs) == 1
    r = runs[0]
    assert r.run_key == "20261001-20261031/run-1"
    assert (r.period_start, r.period_end) == (date(2026, 10, 1), date(2026, 10, 31))
    assert r.expected_rows and not r.warnings


def test_manifest_listing_missing_files_is_flagged(tmp_path):
    base = tmp_path / "c" / "exp" / "20261101-20261130" / "run-2"
    _w(base / "part_0_0001.csv", "date,cost\n")
    _w(base / "manifest.json", json.dumps({"runInfo": {}, "blobs": [{"blobName": "part_0_0001.csv"}, {"blobName": "part_0_0002.csv"}]}))
    runs = discover_runs(LocalExportSource(str(tmp_path)), "c", "exp/")
    assert any("not present yet" in w for w in runs[0].warnings)
    assert runs[0].period_start == date(2026, 11, 1)  # from folder name


def test_legacy_layout_each_file_is_a_run_sorted_by_period(tmp_path):
    _w(tmp_path / "c" / "exp" / "20261001-20261031" / "exp_aaa.csv", "x")
    _w(tmp_path / "c" / "exp" / "20260901-20260930" / "exp_bbb.csv", "x")
    _w(tmp_path / "c" / "exp" / "20260901-20260930" / "readme.txt", "ignored")
    runs = discover_runs(LocalExportSource(str(tmp_path)), "c", "exp/")
    assert [r.period_start for r in runs] == [date(2026, 9, 1), date(2026, 10, 1)]
    assert all(len(r.files) == 1 for r in runs)


def test_local_source_rejects_path_escape(tmp_path):
    src = LocalExportSource(str(tmp_path / "root"))
    (tmp_path / "root" / "c").mkdir(parents=True)
    assert src.list_files("c", "../../") == []
