"""Optional PDF conversion using LibreOffice, when installed on the host."""
from __future__ import annotations
import shutil
import subprocess
import tempfile
from pathlib import Path


class PDFExportUnavailable(RuntimeError):
    pass


def convert_pptx_to_pdf(pptx_bytes: bytes) -> bytes:
    executable = shutil.which("libreoffice") or shutil.which("soffice")
    if not executable:
        raise PDFExportUnavailable("PDF export needs LibreOffice installed on this machine. The editable PPTX is still available.")
    with tempfile.TemporaryDirectory(prefix="hackpack_pdf_") as temp_dir:
        root = Path(temp_dir)
        input_path = root / "hackpack_pitch.pptx"
        input_path.write_bytes(pptx_bytes)
        try:
            result = subprocess.run(
                [executable, "--headless", "--convert-to", "pdf", "--outdir", str(root), str(input_path)],
                check=False, capture_output=True, text=True, timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PDFExportUnavailable("LibreOffice could not convert the presentation. Download the PPTX instead.") from exc
        output_path = root / "hackpack_pitch.pdf"
        if result.returncode != 0 or not output_path.exists():
            detail = (result.stderr or result.stdout or "").strip()[:180]
            raise PDFExportUnavailable(f"PDF export failed. Download the PPTX instead. {detail}")
        return output_path.read_bytes()
