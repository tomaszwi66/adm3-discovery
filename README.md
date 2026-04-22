# ADM-3 - Autonomous Discovery Multi-Agent Framework

> A local autonomous scientific discovery CLI.  
> Generates hypotheses, critiques them, searches the web, runs experiments, and iterates - powered entirely by a local LLM via Ollama. No API keys required.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![Ollama](https://img.shields.io/badge/LLM-Ollama-black?logo=ollama)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Active-brightgreen)

---

## What It Does

ADM-3 takes any research problem and runs a structured multi-agent loop to explore it systematically:

1. **Generates** 10-15 diverse hypotheses with calibrated probabilities
2. **Falsifies** each hypothesis (Skeptic Agent) - drops weak and rejected ones
3. **Searches the web** (DuckDuckGo) and maps novelty against existing literature
4. **Designs and executes** a Python experiment for the best hypothesis
5. **Ranks** all survivors using `EV = Impact × P(correct) × Test Speed`
6. **Issues a binding decision** (Arbiter Agent) - can override the top-ranked hypothesis based on experimental results
7. **Persists memory** to a JSON file per problem - each re-run builds on previous findings

---

## Architecture

```
main.py  (orchestrator)
│
├── agents/
│   ├── generator.py     Step 1 - hypothesis generation
│   ├── skeptic.py       Step 2 - active falsification
│   ├── researcher.py    Step 3 - web search + novelty mapping
│   ├── experimenter.py  Step 4 - experiment design + code generation
│   ├── ranker.py        Step 5 - EV scoring and ranking
│   └── arbiter.py       Step 6 - binding decision + roadmap
│
├── tools/
│   ├── llm.py           Ollama REST API interface
│   ├── search.py        DuckDuckGo search
│   └── executor.py      Sandboxed subprocess code execution
│
└── memory/
    └── store.py         JSON persistence (one file per problem)
```

Each agent calls the LLM with a structured prompt, parses JSON output, and passes enriched data to the next stage. All agents use `json_mode=True` for reliable structured output. Every agent has a graceful fallback - the pipeline never crashes on a bad LLM response.

---

## Quick Start

### 1. Requirements

- Python 3.10+
- [Ollama](https://ollama.com) installed and running

### 2. Install

```bash
git clone https://github.com/tomaszwi66/adm3-discovery.git
cd adm3-discovery
pip install -r requirements.txt
```

### 3. Pull the model

```bash
ollama pull qwen2.5:14b
```

> Any Ollama model works. Smaller models (e.g. `qwen2.5:7b`, `llama3.1:8b`) run faster at lower quality. Edit `config.py` to change the default.

### 4. Run

```bash
python main.py
```

Or pass the problem directly:

```bash
python main.py --problem "Does dopamine regulate synaptic plasticity differently in adolescents vs adults?"
python main.py --problem "What causes protein misfolding in Alzheimer's disease?"
python main.py --iterations 5 --model qwen2.5:7b
```

---

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--problem` / `-p` | interactive prompt | Research problem (skip interactive input) |
| `--iterations` / `-n` | `3` | Number of discovery cycles |
| `--model` / `-m` | `qwen2.5:14b` | Ollama model to use |

---

## Output Format

Each iteration prints a full 10-section ADM-3 report:

```
[1]  Problem Reframed
[2]  Filtered Hypotheses       - table with P(correct), classification, novelty
[3]  Adversarial Analysis      - failure modes and kill conditions per hypothesis
[4]  Prior Art Mapping         - supporting/contradicting evidence from web search
[5]  Experiment Design         - description, variables, success metric + execution output
[6]  Ranking                   - EV scores table (Impact × P × Speed)
[7]  Arbiter Decision          - binding justification + dissenting views
[8]  Selected Best Bet         - winning hypothesis with final P(correct)
[9]  Next Actions              - 7-day and 30-day roadmap
[10] Memory Log Update         - patterns and strategies saved for future runs
```

---

## Real Test Outputs

Three benchmark problems were run on `qwen2.5:14b` at `--iterations 1`.

---

### Problem 1 - Machine Learning

**Input:**
```
Does adding structured noise during transformer attention training improve
generalization on out-of-distribution data?
```

**Pipeline summary:**
```
[Generator]    15 hypotheses generated
[Skeptic]      8 Survive, 2 Weak, 5 Rejected
[Researcher]   Novelty: H9=Partial overlap, H3=Partial overlap, H5=Partial overlap
[Experimenter] Experiment designed  (p_success=70%)
[Executor]     ✓ SUCCESS
[Ranker]       Top: H9  EV=2.24  P=35%
[Arbiter]      Winner: H2  (final P=55%)
               Completed in 324s
```

**Experiment result:**
```
Baseline train MAE:      0.0000
Noise model train MAE:   0.7469
Baseline test (OOD) MAE: 0.0000
Noise model test (OOD):  2.0490
RESULT: REJECTED
```

**Arbiter decision** *(overrode top-ranked H9 based on experiment)*:
> The experiment REJECTED H9. H2 - which suggests structured noise leads to catastrophic forgetting - aligns better with the observed negative effect. Final P=55%.

**Best Bet:** Structured noise disrupts learned representations, leading to catastrophic forgetting and degraded OOD performance.

---

### Problem 2 - Biology

**Input:**
```
Does intermittent fasting alter mitochondrial biogenesis pathways
differently than caloric restriction alone?
```

**Pipeline summary:**
```
[Generator]    15 hypotheses generated
[Skeptic]      10 Survive, 1 Weak, 4 Rejected
[Researcher]   Novelty: H1=Partial overlap, H6=Partial overlap, H2=Partial overlap
[Experimenter] Experiment designed  (p_success=70%)
[Executor]     ✓ SUCCESS
[Ranker]       Top: H1  EV=2.592  P=45%
[Arbiter]      Winner: H1  (final P=55%)
               Completed in 314s
```

**Experiment result:**
```
Mean biomarker for IF: 85.21
Mean biomarker for CR: 73.24
RESULT: SUPPORTED
```

**Best Bet:** Intermittent fasting increases mitochondrial biogenesis more effectively than caloric restriction through enhanced autophagy and metabolic flexibility.

---

### Problem 3 - Physics

**Input:**
```
What are the most promising mechanisms for achieving room-temperature
superconductivity in hydrogen-rich compounds under high pressure?
```

**Pipeline summary:**
```
[Generator]    15 hypotheses generated
[Skeptic]      10 Survive, 0 Weak, 5 Rejected
[Researcher]   Novelty: H1=Partial overlap, H2=Partial overlap, H3=Partial overlap
[Experimenter] Experiment designed  (p_success=70%)
[Executor]     ✓ SUCCESS
[Ranker]       Top: H1  EV=3.024  P=60%
[Arbiter]      Winner: H3  (final P=55%)
               Completed in 334s
```

**Experiment result:**
```
Average Tc with Carbon Chains:    231.33 K
Average Tc without Carbon Chains: 250.00 K
Difference:                        -18.67 K
RESULT: REJECTED
```

**Arbiter decision** *(overrode H1 despite higher EV)*:
> Experiment REJECTED H1 - carbon chain doping reduced Tc by 18.67 K. H3 (graphene-like hybrid structures) offers a more robust mechanism: enhanced electron delocalization without the lattice instability seen with carbon chains.

**Best Bet:** Integration of hydrogen-rich compounds with graphene-like structures - enhanced electron delocalization and reduced scattering under high pressure.

---

## Memory System

Each problem gets its own memory file:

```
memory_does_adding_structured_noise_during_transformer_at.json
memory_does_intermittent_fasting_alter_mitochondrial_biog.json
memory_what_are_the_most_promising_mechanisms_for_achievi.json
```

Re-running the same problem loads prior context - the LLM receives previous best bets, detected patterns, rejected biases, and successful strategies. This enables genuine multi-session refinement.

Memory schema:
```json
{
  "runs": [...],
  "patterns": ["..."],
  "rejected_biases": ["..."],
  "high_yield_domains": [],
  "successful_strategies": ["..."]
}
```

Memory files are excluded from git via `.gitignore`.

---

## Configuration

Edit `config.py` to change defaults:

```python
MODEL        = "qwen2.5:14b"   # default Ollama model
ITERATIONS   = 3               # discovery cycles per run
LLM_TIMEOUT  = 180             # seconds per LLM call
EXEC_TIMEOUT = 30              # seconds for experiment execution
SEARCH_RESULTS = 5             # DuckDuckGo results per query
MAX_MEMORY_RUNS = 20           # oldest runs rotated out beyond this
```

---

## Safety

- Generated experiment code is scanned for dangerous patterns before execution (`os.system`, `subprocess`, `requests`, file writes are blocked)
- Subprocess execution has a configurable timeout (default 30s)
- All agent outputs have JSON parse fallbacks - the pipeline never crashes on a bad LLM response
- Memory is capped at 20 runs to prevent prompt bloat

---

## Known Limitations

- **Synthetic experiments** - the Experimenter generates simulated code, not real lab protocols. Results are indicative, not conclusive.
- **Single model** - all agents share one LLM instance. A real multi-agent system would use specialized models per role.
- **Search quality** - DuckDuckGo results vary; on niche topics you may get "no results" on some queries.
- **Speed** - one full iteration takes ~5-6 min on `qwen2.5:14b`. Use `qwen2.5:7b` or `llama3.1:8b` for faster runs.
- **P(correct) calibration** - probability estimates are LLM-generated, not statistically grounded. Treat them as relative rankings, not absolute probabilities.

---

## Project Structure

```
adm3-discovery/
├── main.py               # CLI entry point + orchestrator
├── config.py             # All tunable parameters + CLI arg parsing
├── requirements.txt      # 2 dependencies: requests, ddgs
├── LICENSE
├── .gitignore
├── agents/
│   ├── __init__.py
│   ├── generator.py
│   ├── skeptic.py
│   ├── researcher.py
│   ├── experimenter.py
│   ├── ranker.py
│   └── arbiter.py
├── tools/
│   ├── __init__.py
│   ├── llm.py
│   ├── search.py
│   └── executor.py
└── memory/
    ├── __init__.py
    └── store.py
```

---

## License

MIT - see [LICENSE](LICENSE)

---

## Author

**Tomasz Wietrzykowski**

Built with [Ollama](https://ollama.com) · [DuckDuckGo Search](https://pypi.org/project/ddgs/) · Python stdlib
