# Benchmark Results

Run:

```bash
python benchmarks/run_benchmarks.py --manifest benchmarks/benchmark_manifest.yaml --output benchmarks/results/latest.json
```

The harness writes both `latest.json` and `latest.md`. Missing fixture PDFs are marked as skipped so benchmark tables stay honest until redistributable fixtures are added.
