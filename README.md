# RailInject & RailGate

**Right Then, Wrong Now: Stopping LLM Agents from Acting on Stale or Injected Orders in Railway Operations**

Yulliwas Ameur, Billal Mokhtari, Samir Chelghoum, Samia Bouzefrane

*Submitted to AI4RAILS 2027 (8th International Workshop on Artificial Intelligence for RAILwayS, co-located with EDCC 2027, Trondheim, Norway, 6 April 2027)*

---

## Overview

Large language model (LLM) agents are entering railway operations: they draft maintenance work orders, propose train reroutes and request speed restrictions. Two risks follow:

1. **Indirect prompt injection**: untrusted text (defect reports, supplier bulletins) carries hidden instructions.
2. **Time-of-check to time-of-use (TOCTOU)**: the agent plans at one moment but executes later; authority may be revoked or the railway state may change.

This repository contains:

- **RailInject** (`code/railinject/`): a benchmark with a rolling-stock maintenance suite (S1) and a dispatching suite (S2) that tests both risks together.
- **RailGate** (`code/railinject/gate.py`): a deterministic gate that decides, inside one serialisable transaction at commit time, whether a queued action still has valid authority, rests on current state, takes its targets from trusted sources and respects operating rules.
- **Episode logs** (`data/runs/`): all 21,976 pre-registered episodes from the LUMI campaign, plus 1,872 variance episodes.
- **Analysis outputs** (`paper/`): generated tables, figures and statistics for the paper.

## Key Results

| Metric | Value |
|---|---|
| Models tested | 4 open-weight (Qwen2.5-7B, Hermes-3-Llama-3.1-8B, Qwen2.5-32B, Qwen2.5-72B) |
| Episodes (temperature 0) | 21,976 |
| Max ASR without defence | 77% (Qwen-72B) |
| ASR with RailGate | **0%** (rule-breaking attacks) |
| Lifecycle violations with RailGate | **0 / 159** |
| Within-rule attacks (G5b) committed | 15% |
| Benign utility drop | 2.3 points |
| GPU hours (MI250X) | 36 |

## Repository Structure

```
.
├── code/
│   ├── railinject/           # Benchmark and gate implementation
│   │   ├── gate.py           # RailGate: commit-time gating
│   │   ├── env.py            # Environment (state store + authority)
│   │   ├── agent.py          # LLM agent loop
│   │   ├── run.py            # Episode runner
│   │   ├── store.py          # SQLite state store
│   │   ├── analyze.py        # Analysis and table generation
│   │   └── suites/           # S1 (depot) and S2 (dispatching) suites
│   ├── tests/                # Unit tests (pytest)
│   └── slurm/                # LUMI job scripts
├── data/
│   └── runs/                 # Episode logs from the LUMI campaign
│       ├── campaign/         # Main campaign (21,976 episodes, T=0)
│       ├── variance/         # Variance runs (1,872 episodes, T=0.7)
│       ├── subset70b/        # Qwen-72B subset
│       └── errors_first_pass/# First-pass errors (re-run once, as registered)
├── paper/
│   ├── stats.json            # Full statistical results
│   ├── fig_tradeoff.pdf      # Trade-off figure
│   ├── supp_prereg.json      # Supplementary pre-registration checks
│   └── variance_runs.json    # Variance analysis
├── LICENSE                   # MIT License
└── README.md                 # This file
```

## Pre-registration

The test-set hash, hypotheses, metrics and analysis code were frozen in a time-stamped commit and registered on OSF before the campaign:

**OSF**: [https://osf.io/y5q7m](https://osf.io/y5q7m) (under embargo until review ends)

Test set SHA-256: `0a604d5f522b366f30ec6c3618fa2a21597062178d7ed4d61079ccd9f7b829fd`

## Reproduction

### Requirements
- Python 3.10+
- vLLM (tested with 0.6.3 on ROCm and 0.8.5 on CUDA)
- 1-4 GPUs depending on model size

### Quick start
```bash
pip install -e code/
pytest code/tests/
```

### Full campaign (requires GPU cluster)
```bash
cd code/slurm
bash setup_login.sh       # download models, verify test-set hash
bash launch.sh pilot      # pilot run (20 episodes per model)
bash launch.sh campaign   # full campaign + analysis
```

## Compute

This work used:
- **EuroHPC LUMI** (project 465003755, allocation DEV-275): MI250X GPUs, ~36 GPU-hours
- **MesoNET Juliet** (project M26297, ANR-21-ESRE-0048): environment setup and tests

## Data Sources

- **MetroPT-3** (UCI Machine Learning Repository, CC BY 4.0): failure reports and signal names for suite S1
- All other data (vehicles, work orders, isolations, network, TSRs) is synthetic

## Citation

```bibtex
@inproceedings{ameur2027railgate,
  author    = {Ameur, Yulliwas and Mokhtari, Billal and Chelghoum, Samir and Bouzefrane, Samia},
  title     = {Right Then, Wrong Now: Stopping {LLM} Agents from Acting on Stale or Injected Orders in Railway Operations},
  booktitle = {Proceedings of the 8th International Workshop on Artificial Intelligence for RAILwayS (AI4RAILS 2027)},
  year      = {2027},
  note      = {Co-located with EDCC 2027, Trondheim, Norway}
}
```

## License

MIT License. See [LICENSE](LICENSE).

## Contact

Yulliwas Ameur — yulliwas.ameur@efrei.fr — Efrei Research Lab / CEDRIC-Cnam
