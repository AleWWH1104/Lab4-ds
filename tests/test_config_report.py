from pathlib import Path

from lab4_ds.config import load_config
from lab4_ds.report import generate_report


def test_official_configuration_has_11_dates_per_lake() -> None:
    config = load_config()
    assert all(len(lake["acquisitions"]) == 11 for lake in config["lakes"].values())
    assert config["lakes"]["amatitlan"]["acquisitions"][6]["date"] == "2026-02-07"


def test_report_without_data_marks_results_pending(tmp_path: Path) -> None:
    config = load_config()
    output = tmp_path / "informe.md"
    markdown, pdf = generate_report(
        config,
        template_path=Path("report/plantilla.md"),
        output_path=output,
        table_root=tmp_path / "missing",
    )
    text = markdown.read_text(encoding="utf-8")
    assert "adquisición en vivo pendiente" in text
    assert "no presenta hallazgos" in text
    assert "![" not in text
    assert pdf is None
