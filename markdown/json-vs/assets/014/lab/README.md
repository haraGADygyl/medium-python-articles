# Lab — 014, JSON vs. Protocol Buffers

Python 3.12.3, `protobuf==7.36.2` (upb backend), `grpcio-tools==1.84.0` (libprotoc
35.1), `msgpack==1.1.0`, `zstandard==0.23.0`, Ryzen 5 3600. The payload is the series'
shared dataset from `../../payload/make_payload.py`.

```bash
pip install protobuf==7.36.2 grpcio-tools==1.84.0 msgpack==1.1.0 zstandard==0.23.0
python -m grpc_tools.protoc -I. --python_out=. buoy.proto
python -m grpc_tools.protoc -Ievolution --python_out=evolution evolution/*.proto
```

The generated `*_pb2.py` files are committed; regenerate them with the commands above
if you change a `.proto`.

| Experiment | Command | Output |
| --- | --- | --- |
| Size (raw, gzip, zstd), single-record size, bytes-only and dict-to-dict timing | `python3 measure.py` | `output-protobuf.txt` |
| Evolution: added field, rename, reused number, proto3 defaults, JSON mapping, `--decode_raw` | `python3 evolution.py` | `output-evolution.txt` |
| The snippet printed in the article (writes `observation.bin`) | `python3 snippets.py` | `output-snippets.txt` |

**Two timings on purpose.** "Bytes only" times `SerializeToString` / `ParseFromString`
on ready-made messages. "Dicts" adds building the messages from the payload's Python
dicts and reading every field back (`convert.py`), which is what code that keeps its
data as dicts pays. Best of five, GC paused; the machine had other load during the run
(load average ~4), and the quoted run matched two others within ~10%.
