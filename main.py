"""
APEX Discovery Multi-Agent Framework (ADM-3)
─────────────────────────────────────────────
Autonomous scientific discovery CLI.
Run with:  python main.py
           python main.py --iterations 5 --model llama3.1:8b
           python main.py --problem "How does caffeine affect adenosine receptors?"
"""
import json
import sys
import textwrap
import time

import config
from agents import generator, skeptic, researcher, experimenter, ranker, arbiter
from memory import store
from tools import executor


# ── Display helpers ───────────────────────────────────────────────────────────

def _hr(char="─", width=72):
    print(char * width)


def _section(title: str):
    print()
    _hr("═")
    print(f"  {title}")
    _hr("═")


def _sub(title: str):
    print()
    _hr("─")
    print(f"  {title}")
    _hr("─")


def _wrap(text: str, indent: int = 4) -> str:
    prefix = " " * indent
    return textwrap.fill(str(text), width=80, initial_indent=prefix, subsequent_indent=prefix)


def print_hypotheses_table(hypotheses: list):
    if not hypotheses:
        print("    (no hypotheses)")
        return
    print(f"  {'ID':<4} {'P%':<5} {'Class':<10} {'Novelty':<18} Hypothesis")
    _hr()
    for h in hypotheses:
        hyp_short = h.get("hypothesis", "")[:52]
        print(
            f"  {h.get('id','?'):<4} "
            f"{h.get('p_correct','?'):<5} "
            f"{h.get('classification','?'):<10} "
            f"{h.get('novelty','-'):<18} "
            f"{hyp_short}"
        )


def print_ranking_table(ranked: list):
    if not ranked:
        print("    (no rankings)")
        return
    print(f"  {'Rank':<5} {'ID':<4} {'EV':<7} {'P%':<5} {'Impact':<8} {'Speed':<7} Hypothesis")
    _hr()
    for h in ranked:
        hyp_short = h.get("hypothesis", "")[:40]
        print(
            f"  {h.get('rank','?'):<5} "
            f"{h.get('id','?'):<4} "
            f"{h.get('ev_score','?'):<7} "
            f"{h.get('p_correct','?'):<5} "
            f"{h.get('impact','?'):<8} "
            f"{h.get('test_speed','?'):<7} "
            f"{hyp_short}"
        )


def print_10_section_report(
    iteration: int,
    problem: str,
    hypotheses: list,
    filtered: list,
    enriched: list,
    experiment: dict,
    exec_result: dict,
    ranked: list,
    decision: dict,
):
    """Render the ADM-3 10-section output to terminal."""

    _section(f"ADM-3 ITERATION {iteration} - DISCOVERY REPORT")

    # [1] Problem Reframed
    _sub("[1] PROBLEM REFRAMED")
    print(_wrap(problem))

    # [2] Filtered Hypotheses
    _sub(f"[2] FILTERED HYPOTHESES  ({len(filtered)} surviving)")
    print_hypotheses_table(filtered)
    for h in filtered[:3]:
        print(f"\n  H{h['id']}: {h.get('hypothesis','')}")
        print(f"    Mechanism : {h.get('mechanism','')}")
        print(f"    P(correct): {h.get('p_correct','?')}%  |  {h.get('justification','')}")

    # [3] Adversarial Analysis
    _sub("[3] ADVERSARIAL ANALYSIS")
    for h in filtered[:5]:
        fm = h.get("failure_modes", [])
        kc = h.get("kill_condition", "-")
        print(f"  H{h['id']} [{h.get('classification','?')}]")
        if fm:
            for f in fm[:2]:
                print(f"    ✗ {f}")
        print(f"    Kill condition: {kc}")

    # [4] Prior Art Mapping
    _sub("[4] PRIOR ART MAPPING")
    for h in enriched[:3]:
        nov = h.get("novelty", "-")
        sup = h.get("supporting_evidence", [])
        con = h.get("contradicting_evidence", [])
        notes = h.get("notes", "")
        print(f"  H{h['id']} → {nov}")
        for s in sup[:2]:
            print(f"    + {s[:100]}")
        for c in con[:1]:
            print(f"    - {c[:100]}")
        if notes:
            print(f"    Note: {notes[:100]}")

    # [5] Experiments
    _sub("[5] EXPERIMENT DESIGN")
    if experiment:
        print(f"  Description : {experiment.get('description','-')}")
        print(f"  Success     : {experiment.get('success_metric','-')}")
        print(f"  Kill crit.  : {experiment.get('kill_criteria','-')}")
        print(f"  Time est.   : {experiment.get('time_estimate','-')}")
        print(f"  P(success)  : {experiment.get('p_success','?')}%")
    if exec_result:
        status = "✓ SUCCESS" if exec_result.get("success") else "✗ FAILED"
        if exec_result.get("timed_out"):
            status = "⏱ TIMED OUT"
        print(f"\n  Execution: {status}")
        stdout = exec_result.get("stdout", "").strip()
        if stdout:
            for line in stdout.splitlines()[-10:]:   # last 10 lines
                print(f"  > {line}")
        stderr = exec_result.get("stderr", "").strip()
        if stderr:
            print(f"  [stderr] {stderr[:200]}")
    else:
        print("  (No experiment executed)")

    # [6] Rankings
    _sub(f"[6] RANKING  (EV = Impact × P × Speed)")
    print_ranking_table(ranked)

    # [7] Arbiter Decision
    _sub("[7] ARBITER DECISION")
    justification = decision.get("justification", "-")
    print(_wrap(justification))
    dissenting = decision.get("dissenting_views", [])
    if dissenting:
        print("\n  Dissenting views:")
        for d in dissenting:
            print(f"    H{d.get('id','?')} P={d.get('p_correct','?')}%: {d.get('reason','')[:100]}")

    # [8] Best Bet
    _sub("[8] SELECTED BEST BET")
    best = decision.get("best_bet", {})
    final_p = decision.get("final_p_correct", "?")
    print(f"  Hypothesis  : {best.get('hypothesis','-')}")
    print(f"  Mechanism   : {best.get('mechanism','-')}")
    print(f"  Final P     : {final_p}%")
    print(f"  Why survived: {best.get('why_survived','-')[:120]}")

    # [9] Next Actions
    _sub("[9] NEXT ACTIONS")
    actions = decision.get("next_actions", {})
    print("  7-Day:")
    for a in actions.get("7_day", []):
        print(f"    → {a}")
    print("  30-Day:")
    for a in actions.get("30_day", []):
        print(f"    → {a}")

    # [10] Memory Log
    _sub("[10] MEMORY LOG UPDATE")
    patterns = decision.get("memory_patterns", [])
    strategies = decision.get("memory_strategies", [])
    biases = decision.get("rejected_biases", [])
    if patterns:
        print("  New patterns:")
        for p in patterns:
            print(f"    • {p}")
    if strategies:
        print("  Successful strategies:")
        for s in strategies:
            print(f"    ✓ {s}")
    if biases:
        print("  Rejected biases:")
        for b in biases:
            print(f"    ✗ {b}")
    if not (patterns or strategies or biases):
        print("  (No new memory entries this iteration)")

    print()


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_iteration(
    iteration: int,
    problem: str,
    memory: dict,
    model: str,
) -> tuple[dict, dict]:
    """
    Execute one full ADM-3 discovery cycle.

    Returns:
        (updated_memory, arbiter_decision)
    """
    print()
    _hr("═")
    print(f"  ITERATION {iteration}  |  Model: {model}")
    _hr("═")
    t_start = time.time()

    memory_ctx = store.format_memory_context(memory)

    # Step 1: Generate
    print("\n[Step 1] Generator Agent")
    hypotheses = generator.generate(problem, memory_ctx, model)
    if not hypotheses:
        print("  No hypotheses generated. Aborting iteration.", file=sys.stderr)
        return memory, {}

    # Step 2: Skeptic
    print("\n[Step 2] Skeptic Agent")
    filtered = skeptic.analyze(hypotheses, problem, model)
    if not filtered:
        print("  All hypotheses rejected. Aborting iteration.", file=sys.stderr)
        return memory, {}

    # Step 3: Researcher
    print("\n[Step 3] Researcher Agent")
    enriched = researcher.research(filtered, problem, model)

    # Step 4: Experimenter (top hypothesis by p_correct)
    print("\n[Step 4] Experimenter Agent")
    top_hyp = max(enriched, key=lambda h: h.get("p_correct", 0)) if enriched else None
    experiment = experimenter.design(top_hyp, problem, model) if top_hyp else {}

    # Execute experiment
    exec_result = {}
    if experiment.get("code"):
        print("  [Executor] Running experiment code...", end=" ", flush=True)
        exec_result = executor.execute_code(experiment["code"])
        status = "✓" if exec_result.get("success") else "✗ (timeout)" if exec_result.get("timed_out") else "✗"
        print(f"{status}")

    # Step 5: Ranker
    print("\n[Step 5] Ranker Agent")
    ranked = ranker.rank(enriched, exec_result, model)

    # Step 6: Arbiter
    print("\n[Step 6] Arbiter Agent")
    decision = arbiter.decide(ranked, enriched, exec_result, problem, model)

    elapsed = time.time() - t_start
    print(f"\n  Iteration completed in {elapsed:.1f}s")

    # Print full 10-section report
    print_10_section_report(
        iteration, problem, hypotheses, filtered,
        enriched, experiment, exec_result, ranked, decision,
    )

    # Step 7: Update memory
    run_data = {
        "iteration": iteration,
        "problem": problem,
        "hypotheses_count": len(hypotheses),
        "filtered_count": len(filtered),
        "top_hypothesis": top_hyp.get("hypothesis", "") if top_hyp else "",
        "experiment_description": experiment.get("description", ""),
        "exec_success": exec_result.get("success", False),
        "exec_stdout_tail": exec_result.get("stdout", "")[-300:],
        "ranked_top": ranked[0] if ranked else {},
        "arbiter_decision": decision,
    }
    memory = store.add_run(memory, run_data)
    memory = store.merge_arbiter_memory(memory, decision)
    store.save_memory(memory)
    print(f"  Memory saved to {config.MEMORY_FILE}  ({len(memory['runs'])} total runs)")

    return memory, decision


def main():
    args = config.parse_args()
    model = args.model
    iterations = args.iterations

    _section("APEX DISCOVERY MULTI-AGENT FRAMEWORK  (ADM-3)")
    print(f"  Model     : {model}")
    print(f"  Iterations: {iterations}")

    # Get research problem
    if args.problem:
        problem = args.problem.strip()
    else:
        print()
        problem = input("  Enter research problem: ").strip()

    if not problem:
        print("No problem entered. Exiting.")
        sys.exit(0)

    # Set memory file specific to this problem
    config.MEMORY_FILE = store.filename_for_problem(problem)

    print(f"\n  Problem : {problem}")
    print(f"  Memory  : {config.MEMORY_FILE}")

    # Load memory
    memory = store.load_memory()
    prior_runs = len(memory.get("runs", []))
    if prior_runs:
        print(f"  Loaded memory: {prior_runs} prior run(s)")
    else:
        print("  No prior memory found - starting fresh.")

    # Run iterations
    last_decision = {}
    for i in range(1, iterations + 1):
        memory, last_decision = run_iteration(i, problem, memory, model)

    # Final summary
    _section("FINAL SUMMARY")
    best = last_decision.get("best_bet", {})
    final_p = last_decision.get("final_p_correct", "?")
    print(f"  Problem      : {problem}")
    print(f"  Best bet     : {best.get('hypothesis','-')}")
    print(f"  Final P      : {final_p}%")
    print(f"  Mechanism    : {best.get('mechanism','-')}")
    print()
    actions = last_decision.get("next_actions", {})
    print("  Immediate next steps:")
    for a in actions.get("7_day", []):
        print(f"    → {a}")
    print(f"\n  Full results saved to: {config.MEMORY_FILE}")
    _hr()


if __name__ == "__main__":
    main()
