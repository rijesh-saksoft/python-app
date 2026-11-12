from pathlib import Path

from app.cli.extract_invoice import main


def test_refuses_a_pdf_before_calling_a_model(tmp_path: Path) -> None:
    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    assert main([str(pdf)]) == 1


def test_refuses_a_missing_file(tmp_path: Path) -> None:
    assert main([str(tmp_path / "missing.png")]) == 1
