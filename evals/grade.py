#!/usr/bin/env python3
"""Grade using-a-debugger skill eval responses.

Walks a responses directory produced by the runner, invokes a grader subagent
per (eval, config, run), and writes grading.json per graded unit.

Response dir schema expected:
  <responses_dir>/
    eval-<id>-<name>/
      eval_metadata.json                # mirror of the eval entry from evals.json
      with_skill/   OR   without_skill/
        run-<N>/
          outputs/response.md

Output:
  <run-dir>/grading.json
  <responses_dir>/grading_summary.json  (aggregate)

The grader subagent is invoked via `claude -p` with a self-contained prompt.
It must return a single JSON object; see GRADER_JSON_SCHEMA below.

Hallucination check:
  The universal no_hallucinated_claims assertion applies to every response.
  The grader extracts claims the RESPONSE itself makes about the codebase
  and verifies each against the mock repo. prior_context facts are treated
  as ground truth and may be reused without re-verification. Any unverified
  claim fails the universal assertion, which is an automatic run failure
  regardless of the per-eval assertion results.
"""

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

GRADER_JSON_SCHEMA = """
{
  "assertions": [
    { "text": "<assertion text>", "passed": true|false, "evidence": "<quote or description>" }
  ],
  "universal": {
    "passed": true|false,
    "claims": [
      { "claim": "<factual claim extracted from response>", "type": "factual|process|quality",
        "verified": true|false, "verification_note": "<how checked or why not>" }
    ]
  },
  "summary": { "passed": <int>, "failed": <int>, "total": <int>, "pass_rate": <float> },
  "grader_notes": "<optional brief note on grading edge cases>"
}
""".strip()


GRADER_PROMPT_TEMPLATE = """You are a grader for the using-a-debugger skill evals. Evaluate whether an agent's response satisfies a list of assertions.

# Eval context

- Eval: {eval_name} (id {eval_id}; bucket: {bucket})
- Kind: {kind}
- Config: {config} / run {run}

## Prior context (treat as ground truth - this is the fictional session state the agent knows)

{prior_context}

## The user's message

{user_message}

## Agent's response to grade

{response}

## Mock repo

The mock repo referenced by this eval is at: {mock_repo}
You may Read and Grep it to verify claims. It is authoritative for any claim the agent makes about "the code".
Facts in the prior_context are also authoritative - do NOT flag them as unverifiable.

# Per-eval assertions

Grade each assertion pass/fail with specific evidence from the agent's response.
Be strict: shape assertions require the response to clearly exhibit the shape. No partial credit.

{assertions_list}

# Universal assertion (always applies)

{universal_assertion}

Separately from the per-eval assertions, do these steps for the universal check:
1. Extract every factual claim the RESPONSE itself makes about the codebase - file paths, library APIs, function names, method signatures, "used by X" claims, line numbers.
2. For each, verify against the mock repo. prior_context facts are ground truth and pass without re-verification.
3. If ANY response-introduced claim is unverifiable or contradicts the repo, universal.passed = false - this is an automatic run failure regardless of the per-eval assertion pass rate.

# Output

Return ONLY a single JSON object matching this schema. No prose before or after:

{json_schema}
"""


@dataclass
class GradingUnit:
    eval_id: int
    eval_name: str
    bucket: str
    kind: str
    config: str
    run: str
    prior_context: str
    user_message: str
    response_path: Path
    output_grading_path: Path
    assertions: list
    universal_assertion: str
    mock_repo: str


def build_grader_prompt(unit: GradingUnit) -> str:
    response_text = unit.response_path.read_text(encoding="utf-8", errors="replace")
    assertions_list = "\n".join(f"{i + 1}. {a}" for i, a in enumerate(unit.assertions))
    return GRADER_PROMPT_TEMPLATE.format(
        eval_name=unit.eval_name,
        eval_id=unit.eval_id,
        bucket=unit.bucket,
        kind=unit.kind,
        config=unit.config,
        run=unit.run,
        prior_context=unit.prior_context,
        user_message=unit.user_message,
        response=response_text,
        mock_repo=unit.mock_repo,
        assertions_list=assertions_list,
        universal_assertion=unit.universal_assertion,
        json_schema=GRADER_JSON_SCHEMA,
    )


def invoke_grader(prompt: str, model: str | None, timeout: int) -> dict:
    cmd = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
        "--tools",
        "Read,Grep,Glob",
        "--disable-slash-commands",
    ]
    if model:
        cmd.extend(["--model", model])
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"_error": f"grader timeout after {timeout}s"}
    if result.returncode != 0:
        return {"_error": f"grader exit {result.returncode}: {result.stderr[:500]}"}

    try:
        wrapper = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return {"_error": f"grader stdout not JSON: {e}; raw={result.stdout[:500]}"}

    inner_text = wrapper.get("result", "") if isinstance(wrapper, dict) else ""
    payload = _extract_json_object(inner_text)
    if payload is None:
        return {
            "_error": f"grader inner payload has no JSON object; raw={inner_text[:500]}"
        }
    try:
        return json.loads(payload)
    except json.JSONDecodeError as e:
        return {
            "_error": f"grader inner JSON failed to parse: {e}; raw={payload[:500]}"
        }


def _extract_json_object(text: str) -> str | None:
    """Extract the first balanced top-level JSON object from a string.

    Handles prose-before-JSON, code-fence wrappers, and trailing prose.
    Returns None if no balanced object can be found.
    """
    if not text:
        return None
    # Strip code fences if present
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        )
    # Find first { and walk balanced braces, respecting strings
    start = stripped.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(stripped)):
        c = stripped[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : i + 1]
    return None


def load_evals(evals_path: Path) -> tuple[dict, dict]:
    data = json.loads(evals_path.read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in data["evals"]}
    universal = data["universal_assertions"][0]["text"]
    return by_id, universal


def discover_units(
    responses_dir: Path, by_id: dict, universal: str
) -> list[GradingUnit]:
    units = []
    for eval_dir in sorted(responses_dir.iterdir()):
        if not eval_dir.is_dir() or not eval_dir.name.startswith("eval-"):
            continue
        try:
            eval_id = int(eval_dir.name.split("-")[1])
        except (IndexError, ValueError):
            continue
        eval_entry = by_id.get(eval_id)
        if not eval_entry:
            print(
                f"WARN: {eval_dir.name} has no matching eval in evals.json",
                file=sys.stderr,
            )
            continue

        for config in ("with_skill", "without_skill"):
            config_dir = eval_dir / config
            if not config_dir.is_dir():
                continue
            for run_dir in sorted(config_dir.iterdir()):
                if not run_dir.name.startswith("run-"):
                    continue
                units.extend(_units_for_run(run_dir, eval_entry, config, universal))
    return units


def _units_for_run(
    run_dir: Path, eval_entry: dict, config: str, universal: str
) -> list[GradingUnit]:
    mock_repo = eval_entry.get("mock_repo", "")
    prior_context = eval_entry.get("prior_context", "")
    response = run_dir / "outputs" / "response.md"
    if not response.exists():
        return []
    return [
        GradingUnit(
            eval_id=eval_entry["id"],
            eval_name=eval_entry["name"],
            bucket=eval_entry.get("bucket", "none"),
            kind=eval_entry["kind"],
            config=config,
            run=run_dir.name,
            prior_context=prior_context,
            user_message=eval_entry["user"],
            response_path=response,
            output_grading_path=run_dir / "grading.json",
            assertions=eval_entry["assertions"],
            universal_assertion=universal,
            mock_repo=mock_repo,
        )
    ]


def grade_unit(unit: GradingUnit, model: str | None, timeout: int) -> dict:
    prompt = build_grader_prompt(unit)
    result = invoke_grader(prompt, model, timeout)
    record = {
        "eval_id": unit.eval_id,
        "eval_name": unit.eval_name,
        "config": unit.config,
        "run": unit.run,
        **result,
    }
    unit.output_grading_path.parent.mkdir(parents=True, exist_ok=True)
    unit.output_grading_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def effective_pass_rate(record: dict) -> float | None:
    """Pass rate for a graded unit with the universal (no-hallucination) check
    gated as a hard fail.

    The universal assertion defines a fabricated command as an automatic run
    failure regardless of how many per-eval assertions passed, so a response that
    invents a debugger command scores 0 here even if its other assertions held.
    Returns None for units that were never graded (no summary, e.g. errored).
    """
    if "summary" not in record:
        return None
    if record.get("universal", {}).get("passed") is False:
        return 0.0
    return record["summary"].get("pass_rate", 0.0)


def summarize(records: list[dict]) -> dict:
    total = len(records)
    errored = [r for r in records if "_error" in r]
    universal_failures = [
        r for r in records if r.get("universal", {}).get("passed") is False
    ]

    pass_rates = [
        rate for r in records if (rate := effective_pass_rate(r)) is not None
    ]
    mean_rate = sum(pass_rates) / len(pass_rates) if pass_rates else 0.0

    # Ungated companion: per-eval assertion pass rate WITHOUT the hallucination
    # gate, so the gating effect is visible rather than silently folded in.
    assertion_only = [
        r["summary"].get("pass_rate", 0.0) for r in records if "summary" in r
    ]
    mean_rate_assertions_only = (
        sum(assertion_only) / len(assertion_only) if assertion_only else 0.0
    )

    by_config: dict[str, list] = {"with_skill": [], "without_skill": []}
    for r in records:
        config = r.get("config")
        rate = effective_pass_rate(r)
        if config in by_config and rate is not None:
            by_config[config].append(rate)

    return {
        "total_units_graded": total,
        "errored": len(errored),
        "universal_failures": len(universal_failures),
        "mean_pass_rate": mean_rate,
        "mean_pass_rate_assertions_only": mean_rate_assertions_only,
        "mean_pass_rate_with_skill": (
            sum(by_config["with_skill"]) / len(by_config["with_skill"])
            if by_config["with_skill"]
            else None
        ),
        "mean_pass_rate_without_skill": (
            sum(by_config["without_skill"]) / len(by_config["without_skill"])
            if by_config["without_skill"]
            else None
        ),
        "errored_units": [
            {
                "eval_name": r["eval_name"],
                "config": r["config"],
                "run": r["run"],
                "error": r["_error"],
            }
            for r in errored
        ],
        "universal_failure_units": [
            {
                "eval_name": r["eval_name"],
                "config": r["config"],
                "run": r["run"],
                "bad_claims": [
                    c
                    for c in r["universal"].get("claims", [])
                    if not c.get("verified", True)
                ],
            }
            for r in universal_failures
        ],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Grade using-a-debugger skill eval responses"
    )
    parser.add_argument(
        "--responses-dir",
        required=True,
        help="Directory containing eval-*/config/run-*/ structure",
    )
    parser.add_argument("--evals", required=True, help="Path to evals.json")
    parser.add_argument(
        "--model",
        default=None,
        help="Model for grader subagent (default: user's configured)",
    )
    parser.add_argument(
        "--timeout", type=int, default=300, help="Timeout per grader call in seconds"
    )
    parser.add_argument("--parallel", type=int, default=4, help="Parallel grader calls")
    parser.add_argument(
        "--only-eval", type=int, default=None, help="Grade only this eval id"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover units and print counts; do not invoke grader",
    )
    args = parser.parse_args()

    responses_dir = Path(args.responses_dir).resolve()
    evals_path = Path(args.evals).resolve()
    by_id, universal = load_evals(evals_path)

    units = discover_units(responses_dir, by_id, universal)
    if args.only_eval is not None:
        units = [u for u in units if u.eval_id == args.only_eval]

    print(f"Discovered {len(units)} grading units in {responses_dir}", file=sys.stderr)
    if args.dry_run:
        for u in units:
            print(f"  {u.eval_name} / {u.config} / {u.run}", file=sys.stderr)
        return

    records = []
    with ThreadPoolExecutor(max_workers=args.parallel) as executor:
        future_map = {
            executor.submit(grade_unit, u, args.model, args.timeout): u for u in units
        }
        for future in as_completed(future_map):
            unit = future_map[future]
            try:
                record = future.result()
            except Exception as e:
                record = {
                    "eval_id": unit.eval_id,
                    "eval_name": unit.eval_name,
                    "config": unit.config,
                    "run": unit.run,
                    "_error": f"grade_unit raised: {e}",
                }
            records.append(record)
            status = "OK" if "_error" not in record else "ERR"
            print(
                f"  [{status}] {unit.eval_name}/{unit.config}/{unit.run}",
                file=sys.stderr,
            )

    summary_path = responses_dir / "grading_summary.json"
    summary = summarize(records)
    summary_path.write_text(
        json.dumps({"summary": summary, "records": records}, indent=2), encoding="utf-8"
    )
    print(f"\nSummary written to {summary_path}", file=sys.stderr)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
