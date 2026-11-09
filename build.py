"""Build and verify the complete book package using standard-library tools."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BOOK = ROOT / "book"
DIST = ROOT / "dist"
PDF_NAME = "build-http-from-scratch.pdf"


def run(command: list[str], *, cwd: Path = ROOT) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def test() -> None:
    run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT / "code" / "stages",
    )
    run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT / "code" / "final",
    )


def book() -> None:
    if shutil.which("xelatex") is None or shutil.which("latexmk") is None:
        raise SystemExit("XeLaTeX and latexmk are required to build the book")
    run(
        [
            "latexmk",
            "-xelatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "main.tex",
        ],
        cwd=BOOK,
    )
    log = (BOOK / "main.log").read_text(encoding="utf-8", errors="replace")
    forbidden = (
        "LaTeX Warning: There were undefined references",
        "LaTeX Warning: Label(s) may have changed",
        "Overfull \\hbox",
        "Overfull \\vbox",
    )
    failures = [message for message in forbidden if message in log]
    if failures:
        raise SystemExit("PDF quality check failed: " + ", ".join(failures))
    DIST.mkdir(exist_ok=True)
    shutil.copy2(BOOK / "main.pdf", DIST / PDF_NAME)
    print(f"Wrote {DIST / PDF_NAME}")


def clean() -> None:
    run(["latexmk", "-C", "main.tex"], cwd=BOOK)
    output = DIST / PDF_NAME
    if output.exists():
        output.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=("all", "test", "book", "clean"))
    args = parser.parse_args()
    if args.target == "clean":
        clean()
        return
    if args.target in {"all", "test"}:
        test()
    if args.target in {"all", "book"}:
        book()


if __name__ == "__main__":
    main()

