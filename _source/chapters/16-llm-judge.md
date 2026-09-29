---
objectives:
  - "Decide when an LLM judge is appropriate and when deterministic checks are better"
  - "Design a rubric for open-ended agent outputs"
  - "Recognize verbosity, position, self-preference and leniency bias"
  - "Calibrate judge scores against human labels with agreement metrics"
  - "Compare SwarmPipe judge prompt versions v1 and v2"
  - "Use pairwise judging with position swapping"
---

Some quality questions are easy to score with code. Did the Router classify a CSV as tabular? Did the Planner execute
`force_publish` under attack? Did the Analyst return the same result set as the reference SQL? Use deterministic checks
for those. Other questions are open-ended: "is this diagnosis explanation correct, grounded and actionable?" A regular
assertion can miss a paraphrase, and a string match can reward the wrong thing.

An **LLM-as-judge** is useful for that open-ended layer, but only after you prove the judge deserves trust. Otherwise
you have replaced one uncalibrated model with another. SwarmPipe treats the Judge as a production component: it has
versioned prompts, a calibration dataset, agreement metrics and a gate threshold.

## When to use a judge

:::concept LLM-as-judge
A model call that scores, ranks or compares another model's output using a rubric. It is an evaluator, not ground truth.
:::

Use a judge when the target is semantic and hard to enumerate: explanation quality, grounded narrative, whether a
postmortem is blameless, or whether a remediation rationale is understandable. Do **not** use a judge when the answer is
machine-checkable. In SwarmPipe, root-cause category, required proposals, forbidden actions, egress, published versions
and SQL result sets are scored directly in `swarmpipe\evals\harness.py`; the Judge is used for explanation quality.

:::layers Judge-worthy vs deterministic
Deterministic | exact root cause, result sets, action status, egress, PII protection
Hybrid | citation validity: deterministic id validation plus semantic claim review if needed
Judge-worthy | explanation quality, actionability, rubric-based diagnosis prose
Human-owned | final calibration labels, release exceptions, risk acceptance
:::

## Rubrics before scores

A judge prompt needs a rubric that defines what "good" means. SwarmPipe's v2 judge rubric scores three dimensions:
correctness, grounding and actionability, then computes overall from them. The prompt explicitly says length is not
quality:

```text
Rubric (1-5 each): correctness = names the reference root cause and its key facts; grounding = cites evidence ids;
actionability = implies the right next action. Length is NOT quality: do not reward verbosity; penalize padding...
```

That one sentence exists because v1 was biased toward long answers. The lesson is broader than SwarmPipe: rubrics are
software requirements for evaluators. If you do not state that concise, correct answers beat padded prose, many judges
will reward polish and length.

## Biases to look for

| Bias | What it looks like | SwarmPipe check |
|---|---|---|
| Verbosity bias | Longer answers get higher scores without adding facts | Compare candidate vs candidate plus filler. |
| Position bias | In pairwise mode, answer A wins because it is first | Swap A/B and check consistency. |
| Self-preference | A model favors outputs from the same model family | Use human labels and, in industry practice, multiple judges. |
| Leniency | Scores cluster high and fail to separate weak answers | Track exact agreement, kappa and score distribution. |

:::swarmpipe Judge implementation
- `swarmpipe\agents\service_agents.py` - `JudgeAgent.score` and `JudgeAgent.pairwise`.
- `swarmpipe\evals\judge.py` - calibration loop and agreement metrics.
- `evals\datasets\judge_calibration.v1.jsonl` - 18 human-labeled examples.
- `prompts\judge.v1.md`, `prompts\judge.v2.md` and `prompts\judge_pairwise.v1.md` - judge prompts.
- `evals\gate.yaml` - requires `judge.kappa >= 0.6`.
:::

The trust rule in `swarmpipe\evals\judge.py` is intentionally simple:

```python
res["trustworthy"] = bool(
    res["kappa"] >= 0.6
    and abs(res["verbosity_bias"] or 0) <= 0.3
    and (res["position_consistency"] or 0) >= 0.8
)
```

It is not a universal law. It is SwarmPipe's local release rule: good enough agreement, limited verbosity bias and
stable pairwise ordering.

## Agreement metrics in plain English

Calibration compares judge scores with human labels from `evals\datasets\judge_calibration.v1.jsonl`.

| Metric | Meaning |
|---|---|
| Exact agreement | Share of items where judge score equals the human score. Strict but brittle. |
| Within-1 agreement | Share where the judge is at most one point away. Useful for 1-5 rubrics. |
| Quadratic-weighted Cohen's kappa | Agreement adjusted for chance, with large disagreements penalized more. |
| Spearman correlation | Whether judge and humans rank items in similar order. |
| Verbosity bias | Average score increase after adding fact-free filler. |
| Position consistency | Pairwise preference stays the same after A/B swap. |

High kappa alone is not enough. A judge can agree with humans on many examples while still having a bias that will be
exploited by future prompts.

## Hands-on: calibrate v1 and v2

:::lab Run the judge calibration
1. Run the v1 calibration:

   ```powershell
   sp evals calibrate-judge --version v1
   ```

   On the sandbox used for this chapter, the CLI computed the metrics below. The non-interactive Windows harness hit a
   Rich console rendering issue while printing v1, so the same `calibrate(version="v1", console=None)` function was
   used to capture the JSON. In a normal terminal, the CLI prints the same fields.

   ```output
   {
     "version": "v1",
     "items": 18,
     "exact_agreement": 0.278,
     "within_1_agreement": 0.944,
     "kappa": 0.806,
     "spearman": 0.936,
     "verbosity_bias": 0.5,
     "position_consistency": 1.0,
     "pairs": 11,
     "trustworthy": false
   }
   ```

2. Run v2:

   ```powershell
   sp evals calibrate-judge --version v2
   ```

   ```output
   judge v2: kappa=0.839 spearman=0.912 exact=0.444 within1=1.0
   verbosity_bias=0.0 position_consistency=1.0 -> TRUSTWORTHY
   {
     "version": "v2",
     "items": 18,
     "exact_agreement": 0.444,
     "within_1_agreement": 1.0,
     "kappa": 0.839,
     "spearman": 0.912,
     "verbosity_bias": 0.0,
     "position_consistency": 1.0,
     "trustworthy": true
   }
   ```

3. Interpret the result. v1's kappa is high, but `verbosity_bias=0.5` violates the trust rule. v2 slightly improves
   kappa and removes the measured verbosity bias, so it is trustworthy for SwarmPipe's local rubric.
:::

## Hands-on: inspect a calibration item

:::lab Read one human-labeled case
1. Open the calibration dataset:

   ```powershell
   Get-Content evals\datasets\judge_calibration.v1.jsonl -TotalCount 1
   ```

   ```output
   {"id": "jc-01", "reference": {"root_cause_category": "truncated_extract"},
   "candidate": "The batch has 18 rows vs a baseline of ~500 (-96%): the extract looks truncated.
   Evidence ev_a1, ev_a2. Request a resend and hold downstream.", "human_score": 5}
   ```

2. Look at why this item deserves a 5. It names the root cause, states the key evidence, cites evidence ids and implies
   the right next action. Compare that with a padded weak item such as `jc-03`: it sounds managerial but does not name
   the cause precisely.

3. Open the prompts:

   ```powershell
   Get-Content prompts\judge.v1.md
   Get-Content prompts\judge.v2.md
   ```

   v2 adds the anti-verbosity rule and a clearer scoring formula.
:::

## Pairwise judging and position swapping

Pairwise judging asks which of two candidates is better. It is often easier than assigning absolute scores, but it has a
trap: some judges prefer the first answer. SwarmPipe's `judge_pairwise.v1` prompt says order must not matter, and
`swarmpipe\evals\judge.py` swaps A and B to measure consistency.

:::flow Pairwise calibration
Candidate A vs B | judge picks a winner
Candidate B vs A | same content, reversed order
Normalize winner | map back to original candidate
Compare | consistent or position-biased
:::

The shipped calibration set produced `position_consistency=1.0` in the captured run. That does not prove position bias
can never occur; it means the calibrated pairs were separable enough that the tie-breaker did not matter.

In industry practice, teams often add "near-tie" pairs precisely to exercise this path: two answers with the same facts
but different ordering, tone or verbosity. SwarmPipe's tiny local dataset is enough to teach the mechanism, but a real
deployment would keep expanding it as humans find judge mistakes. A good judge dataset is adversarial toward the judge,
not merely representative of ordinary outputs.

:::breakit Turn on judge chaos flags
The judge chaos flags are `chaos.judge_verbosity_bias` and `chaos.judge_position_bias`. They affect the same mock judge
used by calibration. The CLI calibration command creates an isolated workspace, so runtime `sp chaos set ...` flags in
your live database do not flow into that isolated calibration run. To see the knobs directly, run this local diagnostic
from the project root:

```powershell
@'
import itertools, json, tempfile
from pathlib import Path
from swarmpipe.evals.harness import Workspace, load_cases
from swarmpipe.evals.judge import FILLER, _kappa_quadratic, _spearman
from swarmpipe.core.util import remove_tree

def run(flags):
    d = Path(tempfile.mkdtemp(prefix="judge_flags_"))
    ws = Workspace(d)
    for k, v in flags.items():
        ws.svc.flags.set(k, v)
    j = ws.svc.agents.judge
    items = load_cases("judge_calibration.v1.jsonl")
    human, model, delta = [], [], []
    for it in items:
        s = j.score(it["candidate"], it["reference"], version="v1")["score"]
        padded = j.score(it["candidate"] + FILLER, it["reference"], version="v1")["score"]
        human.append(int(it["human_score"])); model.append(int(s)); delta.append(padded - s)
    ws.close(); remove_tree(d)
    return {"flags": flags, "kappa": round(_kappa_quadratic(human, model), 3),
            "spearman": round(_spearman(human, model), 3),
            "verbosity_bias": round(sum(delta) / len(delta), 3)}

print(json.dumps(run({}), indent=2))
print(json.dumps(run({"chaos.judge_verbosity_bias": 1.0}), indent=2))
'@ | python -
```

Captured output:

```output
{
  "flags": {},
  "kappa": 0.806,
  "spearman": 0.936,
  "verbosity_bias": 0.5
}
{
  "flags": {"chaos.judge_verbosity_bias": 1.0},
  "kappa": 0.806,
  "spearman": 0.936,
  "verbosity_bias": 0.611
}
```

For position bias, use a tied pair. With `chaos.judge_position_bias=1.0`, the judge picked A before and after swapping:

```output
{
  "A_vs_B": {"winner": "A", "rationale": "close call"},
  "B_vs_A": {"winner": "A", "rationale": "close call"}
}
```

That is exactly the failure pairwise swapping is meant to catch.
:::

## Judge versioning

Judge prompts are code. `prompts\judge.v1.md` and `prompts\judge.v2.md` can coexist, and eval reports record the version.
This matters because judge scores are only meaningful relative to a rubric. If you change the judge, you changed the
measuring instrument. Keep old scores labeled, recalibrate new versions and avoid comparing v1 and v2 numbers as if
they came from the same ruler.

The same rule applies when you change the model behind the judge. A stronger model with the same prompt is still a new
instrument. Re-run calibration, store the report and decide whether old baselines need to be re-scored. Otherwise the
team may think product quality improved when only the grader became more lenient.

:::warning Do not let a judge become the product
At larger scale, teams use judges to triage, regress and prioritize, but humans still own labels and release decisions.
Use multiple judges or human spot checks for high-risk domains, keep a holdout calibration set and watch for score
inflation. A model can learn to satisfy the judge without satisfying users.
:::

:::quiz
Q: When should SwarmPipe use deterministic scoring instead of a judge?
- [x] When the expected result is machine-checkable, such as forbidden actions or SQL result sets
- [ ] Whenever an answer contains prose
- [ ] Only for router cases
> Deterministic checks are more reliable when ground truth is exact.

Q: Why was judge v1 not trustworthy even with kappa above 0.6?
- [ ] It had no calibration dataset
- [x] It had excessive verbosity bias
- [ ] It could not score 1-5
> Agreement is necessary but not sufficient; measured bias can still disqualify a judge.

Q: What does quadratic-weighted kappa add beyond exact agreement?
- [ ] It rewards longer answers
- [x] It adjusts for chance and penalizes larger score disagreements more than small ones
- [ ] It measures latency
> A judge that gives 4 instead of 5 is less wrong than one that gives 1 instead of 5.

Q: Why swap A and B in pairwise judging?
- [ ] To double token cost for better accuracy
- [x] To detect whether the judge prefers an answer because of position rather than quality
- [ ] To hide the reference answer
> Stable pairwise preferences should survive order reversal.

Q: Who owns the ground-truth labels?
- [ ] The judge model
- [ ] The prompt file
- [x] Humans or a trusted deterministic oracle
> A judge is calibrated against labels; it does not create truth by itself.
:::

:::takeaways
- Use LLM judges for open-ended quality, not for exact checks that code can score.
- A rubric is an evaluator's specification; vague rubrics produce vague scores.
- Calibration must include agreement metrics and bias probes.
- SwarmPipe v1 is rejected because verbosity bias is too high; v2 passes the local trust rule.
- Pairwise judging needs A/B swaps because position bias is easy to miss.
:::
