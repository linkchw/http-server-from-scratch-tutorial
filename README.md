# Build HTTP from Scratch

This repository contains the complete source package for **Build HTTP from
Scratch: A 12-Week Journey from Python Sockets to a REST API — Mentoring
Edition**.

## Requirements

- Python 3.12 or newer
- XeLaTeX and `latexmk` for the book
- The Noto Serif, Noto Sans, and JetBrains Mono fonts

The server, API, tests, and build helper use only the Python standard library.

## One-command verification

```console
python build.py all
```

The command tests the progressive examples, runs the final framework and API
test suites, compiles the PDF, checks the build log, and places the finished
book at `dist/build-http-from-scratch.pdf`.

Useful narrower commands are:

```console
python build.py test
python build.py book
python build.py clean
```

## Run the final Task API

```console
cd code/final
python -m task_api --database tasks.db
```

The API listens on `http://127.0.0.1:8080`. Try it with the standard-library
client:

```console
python client_example.py
```

The server intentionally implements a strict, documented subset of HTTP/1.1.
It is an educational system, not a production deployment target.

