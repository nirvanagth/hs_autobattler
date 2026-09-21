# R2-B DAgger disagreement-weight ablation

Date: 2026-09-20  
Parent checkpoint: Pointer BC  
Aggregated rows: 914,721, including 30.0% DAgger rows  
Weighted disagreement rows: 3,969

## Contract

- Weights: 0x (no DAgger), 1x, 5x, 10x.
- Seeds: 17, 42, 73.
- DAgger variants initialize from the same Pointer BC checkpoint.
- Five fine-tuning epochs, batch size 512, learning rate 1e-4.
- Same selected DAgger episodes for 1x, 5x, and 10x.
- Evaluation: 200 paired-seat games against ES and 200 against SmartBot.
- Shared holdout seed base: 80,000.

Manifest hashes:

- 1x: `aa4bf349a19fe6747d69d55592acddbddb047c22037d9a12d43810f2e1d5c1d9`
- 5x: `b124e0ec59fb3b9bc580cce12023a9f6baec3081c6c442b345db4b59f0fc3fa8`
- 10x: `6a5b1bee91f8756c52b5cfb4524b3c9514e991be12b0a1537020abaa0e06015e`

## Results

| Weight | Seed | ES win rate | SmartBot win rate |
|---:|---:|---:|---:|
| 0x | 17 | 57.0% | 87.5% |
| 0x | 42 | 56.5% | 84.0% |
| 0x | 73 | 52.0% | 87.5% |
| 1x | 17 | 56.0% | 86.0% |
| 1x | 42 | 59.5% | 85.5% |
| 1x | 73 | 57.5% | 86.5% |
| 5x | 17 | 61.0% | 87.5% |
| 5x | 42 | 59.5% | 87.5% |
| 5x | 73 | 61.5% | 86.0% |
| 10x | 17 | 62.0% | 87.5% |
| 10x | 42 | 58.5% | 88.5% |
| 10x | 73 | 56.0% | 86.5% |

Mean ± sample standard deviation:

| Weight | ES win rate | SmartBot win rate |
|---:|---:|---:|
| 0x | 55.17 ± 2.75% | 86.33 ± 2.02% |
| 1x | 57.67 ± 1.76% | 86.00 ± 0.50% |
| 5x | **60.67 ± 1.04%** | 87.00 ± 0.87% |
| 10x | 58.83 ± 3.01% | **87.50 ± 1.00%** |

## Interpretation

One-times weighting provides a modest ES improvement and reduces variance.
Five-times weighting improves every seed against ES, gives the best ES mean,
and has the lowest ES variance. Ten-times weighting slightly improves the
SmartBot mean but increases ES variance and produces a weak seed73 result.

The balanced promotion decision is therefore **5x disagreement weight**. The
claim is about matched empirical performance, not the unsupported turn-5
recovery mechanism tested in R1.

## Promoted artifacts

- Seed17 SHA-256:
  `7e1df2a123d00a806461fecfb85b583e858de4401560b0225e2a69b00aaee474`
- Seed42 SHA-256:
  `a4c05fc416e4af9ead9837950c3e365a11d05c50764ffe07fee2cd35e4b5fb6c`
- Seed73 SHA-256:
  `c6c02a08dbf3fd6eb05c043717d8b07539694246c2afbf0b5288c668f4fcd7dc`

