# Qualification and measurement protocol

Freeze profile, seeds, exact population, source and native binary identities before comparing results. A positive baseline and candidate each consume the same TSV derived from the same validated JSONL. The independent oracle consumes JSONL. The bundle verifier checks JSONL/TSV consistency, local file hashes, source drift, semantic populations and declared release decisions.

Qualification integrity and release acceptance are separate. Integrity passes only when both positive runs qualify and all requested unsafe controls fail. Release acceptance also requires each positive run's minimum valid-signal count and optional instrumented kernel p99 limit. A correct but too-slow candidate can receive failed release acceptance without implying that the checker broke. No complete application latency acceptance is implemented yet.

For each positive run report exact offered event count, prediction deliveries, duplicate dispositions, oracle disposition histogram, qualified valid signals, admitted actions, final live reservations, numerical difference, failing slices and timing population. Failed candidates never receive a qualified cost denominator.

Kernel-call timing covers `Kernel::step` surrounded by `steady_clock`. It includes instrumentation and the implementation's result handling; it excludes parsing, model computation, queueing, serialization and file/network I/O. The process wall measurement includes native startup, TSV parsing, steps, serialization and local file I/O, but excludes fixture construction and the independent checker. Neither is wire latency, a real-time guarantee or a deployment capacity measurement. Do not sum component percentiles. Observed maxima are not proved worst-case bounds.

The million-event matrix has four seeds and repeated directed controls, plus random synthetic episodes. Seeded episodes deliberately reorder predictions, market updates and terminal deliveries. A terminal sweep closes known reservations before the next session; truncation retains final live obligations. This matrix is not held-out production data and does not model every exchange fault.

Local digests detect alteration relative to a trusted manifest. An attacker can replace both an unsigned manifest and its data; no origin authentication, trusted timestamp, remote attestation or authenticated custody is established. `qualification.verify` also requires matching source, so a code change requires new qualification or reproducing the original source revision.

Cost is optional and supplied by the operator. No hardware/cloud rate is invented. The cost denominator spans the declared positive experiments, including separate baseline and candidate runs. Zero accepted work yields undefined cost, not zero. Lower allocated cost is not necessarily lower cash spending. Trading P&L, customer savings and commercial revenues are not inferred.

Official STAC comparison requires authorized workload specifications and audit conditions. This profile carries its own name. [Public audited GH200 STAC summary](https://docs.stacresearch.com/SMC250910).
