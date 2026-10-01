# Recorded local native qualification

Recorded 2026-10-01 on an arm64 macOS workstation. The raw bundles remain locally under `evidence/runs/million-qualified` and `evidence/runs/budget-rejection`, excluded from Git. The published report and manifest preserve file/source/build identities; they cannot substitute for obtaining raw traces or reproducing the run. CI publishes its smaller complete bundles as workflow artifacts.

| Check | Result |
|---|---|
| Unit/integration tests | 36 passed |
| Fixture events across seeds 7, 19, 41, 73 | 1,000,000 offered events, including repeated directed controls |
| Positive native transitions | 2,000,000 across eight baseline/candidate runs |
| Positive semantic mismatches | 0 |
| Unsafe semantic/trace controls | 12 detected |
| Qualification integrity | pass |
| Declared workstation release acceptance | pass; minimum one valid signal per run, no timing ceiling |
| Independent bundle replay | 20 runs rechecked; local hashes, input consistency and source identity matched |
| Budget-rejection demonstration | Semantic qualification pass; release acceptance fail under a zero-nanosecond kernel p99 ceiling |

## Instrumented step timing

These are local instrumented `Kernel::step` samples, excluding parsing, prediction, queueing, serialization and network I/O. They are not tick-to-trade, model inference, wire latency, a calibrated hardware comparison or a worst-case proof. No inference or accelerator speedup is established. The observed scheduling tails remain visible.

| Seed | Variant | Samples | p50 ns | p99 ns | p99.9 ns | Observed max ns |
|---|---|---:|---:|---:|---:|---:|
| 7 | baseline | 250,000 | 42 | 125 | 208 | 14209 |
| 7 | equivalent | 250,000 | 42 | 125 | 209 | 17833 |
| 19 | baseline | 250,000 | 41 | 84 | 167 | 19459 |
| 19 | equivalent | 250,000 | 42 | 125 | 208 | 18709 |
| 41 | baseline | 250,000 | 42 | 125 | 208 | 67334 |
| 41 | equivalent | 250,000 | 42 | 125 | 208 | 29583 |
| 73 | baseline | 250,000 | 42 | 125 | 167 | 25250 |
| 73 | equivalent | 250,000 | 42 | 125 | 292 | 196750 |

The same binary runs both variants. The candidate adds a small numerical perturbation; it is not an optimized GPU backend. Numerical similarity can fail exact decisions near a threshold, as the test suite demonstrates. The random fixtures use a toy arithmetic predictor, not historical market data.

No allocated cost was supplied, so cost per accepted signal is unknown. CUDA, NIC/DPU, FPGA/ASIC, live exchange, official STAC and enterprise operation remain unqualified/unimplemented.

[Raw report summary](local-million-report.json) · [local manifest](local-million-manifest.json) · [budget demonstration](local-budget-report.json) · [measurement protocol](../docs/EVIDENCE.md)
