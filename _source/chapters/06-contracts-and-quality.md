---
objectives:
  - "Explain why a completed job can still produce incorrect data"
  - "Read SwarmPipe data contracts as versioned code and describe proposed-versus-active lifecycle"
  - "Distinguish breaking schema drift, additive drift and rename mapping"
  - "Describe typed transforms, row-level rejects and the data-assurance check catalogue"
  - "Run quality, freshness and unknown-dataset onboarding labs safely"
---

The most dangerous data failure is the one that looks green. A CSV can parse, a task can finish and a table can load
while every dashboard downstream is wrong. "Ended OK" only proves the program reached the end; it does not prove the
data is complete, current, typed correctly or fit for the business question.

SwarmPipe puts correctness checks inside the workflow. Contracts define what a dataset means. Transforms type and
reject rows. Data assurance checks decide whether to publish or quarantine. Agents help explain drift and propose
changes, but deterministic code trips the circuit breaker.

## Contracts as code

:::concept Data contract
A data contract is an executable agreement between a producer and consumers: dataset name, columns, types, required
fields, keys, freshness, quality checks, references, owners and classification. It is stronger than a schema because it
states what must be true for the data to be trusted.
:::

In SwarmPipe, reviewed contracts live in `config/contracts/*.yaml`. At `sp init`, `ContractStore.sync_from_files`
imports newer YAML versions as active. Runtime proposals are different: agents can create `proposed` versions, but only
a human approval activates them. That gives you GitOps for known datasets and a governed path for new or changed data.

:::swarmpipe Contract lifecycle
`swarmpipe/data/contracts.py` says YAML files are the reviewed source of truth. Proposed versions are stored in the
state DB and only become active through approval.

```python
def propose(self, dataset: str, contract: dict, by: str, note: str) -> int:
    latest = self.svc.db.scalar("SELECT MAX(version) FROM contract_versions WHERE dataset=?", ...)
    version = latest + 1
    self.svc.db.insert("contract_versions", {
        "dataset": dataset, "version": version,
        "contract": dumps(body), "status": "proposed",
        "created_by": by, "change_note": note})
    return version
```
:::

Contracts also carry aliases from the business glossary. That matters when a producer renames `customer_id` to
`client_code`: a name-only comparison is weak, but aliases, type compatibility and value patterns together can support
a mapping. SwarmPipe's `schema_diff` reports missing required columns, optional columns, new columns, alias mappings
and rename candidates. A breaking rename quarantines until approved remediation; an additive column warns and can still
publish because existing consumers can ignore it.

:::flow Contract decision path
Observed columns | from profiling
Schema diff | required missing? new columns?
Steward proposal | mapping or contract update
Critic review | independent evidence
Human approval | for new active contract or high-impact action
Transform and checks | typed data or quarantine
:::

## Typed transforms and row-level rejects

SwarmPipe reads files as strings first, then applies a contract. This separation is important. The reader should not
guess that `"0012"` is an integer if the contract says it is a code; the transform should not silently coerce a bad
date to null and publish it.

:::swarmpipe Transform layer
`swarmpipe/data/transforms.py` maps columns, casts types, rejects rows with required nulls or cast failures, removes
duplicate primary keys and evaluates derived columns with the safe expression engine.

```python
typed, failed = cast_column(df[name], spec, (date_hints or {}).get(name))
out[name] = typed
if spec.get("required"):
    reject_reason = reject_reason.mask(failed & (reject_reason == ""), f"cast_failed:{name}")
...
stats = {"rows_in": rows_in, "rows_out": len(typed_df),
         "rejected": int(rejected_mask.sum()),
         "duplicates_removed": dup_removed}
```
:::

Business rules and derived columns use `swarmpipe/data/safe_expr.py`, not Python `eval`. The expression language parses
AST nodes, allows only known column names and a short list of vectorized functions, and rejects everything else. That is
an agent security control as much as a data-quality feature: model- or user-authored checks must never become arbitrary
code execution.

## Five data-health signals

SwarmPipe's profiler names the five data-health signals explicitly: **freshness, volume, schema,
distribution/quality and lineage**. Quality checks turn those signals into decisions.

| Signal | What it catches | SwarmPipe examples |
|---|---|---|
| Freshness | late arrival or stale business dates | `freshness_overdue`, `data_freshness` |
| Volume | row count too low or too high | `row_count_min`, `volume_vs_baseline` |
| Schema | required columns missing, aliases, new columns | `schema_required_columns`, `schema_new_columns` |
| Distribution/quality | PSI drift, invalid values, reject/null rates, ranges, regex, rules | `distribution_psi:amount`, `accepted_values:channel`, `range:unit_price` |
| Lineage | references and reconciliation across datasets | `referential:customer_id`, `control_total:amount` |

:::swarmpipe Quality checks and circuit breaker
`swarmpipe/data/quality.py` defines the semantics: `pass`, `warn` and `fail`. A fail quarantines the batch and prevents
publish; a warn can publish but raises a signal.

```python
Semantics:
  pass  - fine
  warn  - publish, but raise a signal
  fail  - circuit breaker: the batch is quarantined and NOT published
Row-level violations below a rule's threshold are quarantined individually ("mostly" semantics);
above the threshold the whole batch fails.
```
:::

"Mostly" semantics are the practical compromise. If 3 rows out of 10,000 have an invalid optional category, quarantine
those rows and publish the rest with a warning. If 30% of rows are invalid, that is not noise; it is a producer or
contract failure, so the whole batch fails. The circuit breaker means `d_publish` stages a quarantined version table
instead of repointing the consumer view. Consumers keep the last good published version.

Precision matters more than coverage. A check catalogue with hundreds of noisy warnings teaches operators to ignore
agents. SwarmPipe uses severities, `incidents.min_severity`, row-level thresholds and evals with a clean-day false
positive case to keep alerts useful.

## Hands-on

Start from a clean baseline unless told otherwise:

```powershell
sp reset --yes
sp init
sp scenarios drop baseline --process
```

Ids, dates and timings vary. The examples below are trimmed from a real run.

:::lab Volume drop: green job, bad data
1. Drop a truncated sales file:

   ```powershell
   sp scenarios drop volume_drop --process
   sp runs list --workflow ingest_dataset --limit 4
   ```

   ```output
   dropped ['sales_2026-09-29.csv'] into ...\data\inbox
   admitted 1 file(s); processed in 4.7s
   | workflow       | status      | n  |
   | ingest_dataset | quarantined | 1  |
   | ingest_dataset | succeeded   | 11 |
   ```

2. Find the quarantined `ingest_dataset` run and inspect it:

   ```powershell
   sp runs show <run_id>
   ```

   ```output
   {
     "workflow": "ingest_dataset",
     "dataset": "sales_daily",
     "status": "quarantined",
     "context": {"result_status": "quarantined"},
     "current_step": "lineage"
   }
   | step           | status    |
   | load           | succeeded |
   | transform      | succeeded |
   | quality        | succeeded |
   | publish        | succeeded |
   | lineage        | succeeded |
   ```

   The workflow steps succeeded because they did their jobs. The result is still `quarantined` because `quality`
   found failed checks such as `row_count_min` and `volume_vs_baseline`.

3. In **Runs**, open the run and expand **Data assurance checks**. In **Incidents**, the root cause is
   `truncated_extract`. In **Datasets & Lineage**, `sales_daily` still points to the last good version.
:::

:::lab Unit change, referential break and additive drift
1. Try a distribution and range failure:

   ```powershell
   sp scenarios drop unit_change --process
   sp incidents list --limit 5
   ```

   ```output
   | status    | severity | dataset     | root_cause          | title              |
   | mitigated | high     | sales_daily | unit_or_scale_change | ... range:unit_price (fail: 418 rows ...) |
   ```

2. Try an additive schema change:

   ```powershell
   sp scenarios drop additive_drift --process
   sp incidents list --limit 5
   sp approvals list --status pending
   ```

   ```output
   | status            | severity | dataset     | title                                      |
   | awaiting_approval | warning  | sales_daily | sales_daily: schema drift - schema_new_columns (warn: ['promo_code']) |
   ...
   | kind   | subject                 | risk   |
   | action | notify_owner on sales_daily | low |
   ```

   Additive drift warns because `promo_code` is unknown, but the existing contract columns can still publish. The
   agent recommends follow-up instead of blocking consumers.

3. For a lineage check, run:

   ```powershell
   sp scenarios drop referential_break --process
   sp incidents list --limit 5
   ```

   In **Runs -> Data assurance checks**, look for `referential:customer_id`. The incident root cause is
   `referential_integrity_break`.
:::

:::lab Freshness and unknown-dataset onboarding
1. Advance the business clock through the scenario:

   ```powershell
   sp scenarios drop freshness --process
   sp incidents list --limit 8
   ```

   ```output
   | status    | severity | dataset     | root_cause               | title                         |
   | mitigated | high     | sales_daily | late_or_missing_delivery | sales_daily is overdue ...    |
   | mitigated | high     | inventory   | late_or_missing_delivery | inventory is overdue ...      |
   ```

   `sales_daily` has a 24-hour SLA plus 2-hour grace (1560 minutes). `inventory` has 24 hours plus 1 hour.

2. You can run the clock directly too:

   ```powershell
   sp chaos advance-clock 1560
   sp chaos clear
   ```

3. Onboard a new dataset:

   ```powershell
   sp scenarios drop new_dataset --process
   sp approvals list --status pending
   ```

   ```output
   dropped ['vendors_q3.csv'] into ...\data\inbox
   | workflow       | status  | n |
   | ingest_dataset | waiting | 1 |
   ...
   | kind                | subject    | risk   |
   | contract_onboarding | vendors@v1 | medium |
   ```

4. Review the contract in **Approvals**. If it looks right, approve it:

   ```powershell
   sp approvals approve <approval_id> --as oncall --comment "Contract proposal reviewed"
   sp ask "how many rows in vendors"
   ```

   The waiting run resumes, activates `vendors@v1`, transforms the batch and publishes it.
:::

## Break it: make a threshold too strict

:::breakit Alert fatigue from a bad threshold
In your own SwarmPipe project, open `config\contracts\sales_daily.yaml` and make a harmless threshold too strict, for
example lowering a row-level `max_violation_rate` or increasing `volume.min_rows` beyond normal daily volume. Then run:

```powershell
sp reset --yes
sp init
sp scenarios drop baseline --process
sp scenarios drop clean_day --process
```

You will get noisy incidents for data that should be normal. Restore the file afterward with your editor or, if you are
using git in your own clone, with `git restore config\contracts\sales_daily.yaml`. The lesson is not "never check"; it
is "set thresholds where an alert means action."
:::

For a governed thought experiment, use policy what-if instead of actually publishing bad data:

```powershell
sp policy force_publish --dataset sales_daily --tenant default --confidence 0.9 --blast 3 --no-injection --no-regulated
```

`force_publish` exists, but it is deliberately high risk. Chapter 21 explains the policy and autonomy ladder.

## Production notes

:::warning Checks are product decisions
Industry practice goes beyond SwarmPipe here: every quality rule should have an owner, a remediation path and a known
consumer impact. If nobody knows what to do when a rule fires, it is an expensive log line, not a control.
:::

At larger scale, baseline windows, PSI buckets and freshness SLAs need calendar awareness: weekends, holidays, source
maintenance windows and regional cutoffs. SwarmPipe's injectable business clock makes the idea testable locally; a
production system would connect it to a real business calendar and source SLAs.

## Quiz

:::quiz
Q: Why can an `ingest_dataset` run show succeeded steps but an overall quarantined result?
- [ ] The CLI printed the wrong status
- [x] The workflow executed correctly, but data-assurance checks failed and the circuit breaker prevented publish
- [ ] The Router always quarantines CSV files first
> A successful program execution is not the same as correct data. The quality decision controls publication.

Q: What is the difference between an active and proposed contract version?
- [x] Active contracts are used by ingestion; proposed versions wait for approval
- [ ] Proposed contracts are always used immediately for new files
- [ ] Active contracts exist only in YAML, not the database
> YAML imports create active reviewed versions. Agent-authored contracts remain proposed until a human approves them.

Q: Why is additive drift usually less dangerous than a breaking rename?
- [ ] New columns are always useless
- [x] Existing contract columns are still present, so existing consumers can continue while the new column is reviewed
- [ ] Additive drift bypasses quality checks
> `schema_new_columns` warns. Missing required columns fail.

Q: What does "mostly" semantics mean for row-level checks?
- [ ] Ignore all bad rows if most rows are good
- [x] Quarantine a small rate of bad rows, but fail the whole batch when the violation rate exceeds the threshold
- [ ] Publish everything and create a dashboard warning
> This balances availability with correctness.

Q: Which component evaluates business-rule expressions safely?
- [ ] Python `eval`
- [x] `swarmpipe/data/safe_expr.py`
- [ ] The dashboard
> The safe expression interpreter validates AST nodes, names and functions before evaluating vectorized pandas expressions.
:::

:::takeaways
- "Ended OK" is not "correct"; checks must run inside the workflow before publish.
- Contracts are versioned code: YAML imports reviewed active versions, while agent proposals wait for approval.
- Breaking schema drift quarantines; additive drift can warn and publish when existing contract columns are intact.
- Typed transforms reject bad rows explicitly and feed reconciliation counts.
- The circuit breaker quarantines failed batches so consumers keep the last good version.
- Freshness is a business-clock promise, not just a file-arrival timestamp.
:::
