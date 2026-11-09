# Progressive server snapshots

Each directory freezes one point in the learning journey. Run a snapshot from
its own directory with `python server.py`, then inspect it beside the matching
book chapter. All snapshots bind to loopback only.

1. `01_fixed_response`: accept one connection and send one fixed response.
2. `02_buffered_request`: receive until the complete header section arrives.
3. `03_request_parser`: turn wire bytes into a structured request.
4. `04_response_serializer`: generate byte-correct responses.
5. `05_router`: dispatch by method and path.
6. `06_json_middleware`: introduce request/response objects and middleware.
7. `07_bounded_concurrency`: use a finite worker queue.
8. `08_tinyhttp`: the reusable framework package.
9. `09_task_api`: the completed SQLite REST API.

The last two are exact, tested copies of the final teaching packages. Run all
snapshot checks from this directory with:

```console
python -m unittest discover -s tests -v
```

