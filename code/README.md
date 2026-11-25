# RailInject / RailGate — code of the AI4RAILS 2027 paper (chantier 09)

*Right Then, Wrong Now: Stopping LLM Agents from Acting on Stale or Injected Orders in Railway Operations.*

## What is here

| Path | Content |
|---|---|
| `railinject/store.py` | Versioned state store **and** delegation authority (grants, epochs, revocations, used request identifiers) in one SQLite database; serialisable transactions (`BEGIN IMMEDIATE`). |
| `railinject/gate.py` | Proposal queue and commit-time gate. Checks: N (request identifier not reused), C1 authority, C2 freshness, C3 provenance, C4 invariants. Policies D0–D7 and the three ablations. Ed25519-signed grants. |
| `railinject/env.py` | Episode: tools seen by the agent, read set, provenance labels, lifecycle events, and the ground-truth oracle evaluated at the write instant. |
| `railinject/suites/s1_depot.py` | S1 — rolling-stock depot maintenance (alerts from the MetroPT-3 failure reports; isolations, class-A orders, inspections, crews). |
| `railinject/suites/s2_network.py` | S2 — dispatching and temporary speed restrictions on a small synthetic line (possessions, TSRs, measurements, routes). |
| `railinject/agent.py` | LLM agent (OpenAI-compatible tool calling, served by vLLM) and a scripted agent used only to test the benchmark. |
| `railinject/run.py` | Campaign runner (JSONL, resumable, shardable, parallel episodes). |
| `railinject/analyze.py` | Pre-registered metrics, Wilson intervals, exact McNemar + Holm, cluster bootstrap by user task; writes `results_measured.tex`, table rows and the figure for the paper. |
| `slurm/` | MesoNET Juliet scripts: `setup_login.sh`, `launch.sh pilot|estimate|campaign`, job scripts. |
| `tests/` | Design tests with scripted agents (no LLM): `python -m pytest -q tests`. |

## Benchmark size

44 test user tasks (S1: 24, S2: 20) + 8 development tasks; 20 injection tasks; each user task paired with 4 injection tasks (176 pairs per framing, 3 framings); 60 lifecycle cases (15 per class: authority change, unsafe state change, stale basis, concurrent change). One run = 632 episodes per model and defence.

## Run

```bash
# on the Juliet login node, once
bash slurm/setup_login.sh            # venv, models, detector, revisions, test-set hash
# pre-register (OSF) with runs/TEST_SET_SHA256.txt and runs/MODEL_REVISIONS.json, then:
bash slurm/launch.sh pilot           # 20 items per model, D0 and D7
bash slurm/launch.sh estimate        # seconds per episode -> check the budget
bash slurm/launch.sh campaign        # everything + analysis job (results in runs/paper)
```

Copy `runs/paper/{results_measured.tex,tab_main_rows.tex,tab_life_rows.tex,fig_tradeoff.pdf}` next to `main.tex` and recompile: the red "??" are replaced automatically.
