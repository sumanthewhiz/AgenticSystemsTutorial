---
objectives:
  - "Explain immutable dataset versions, blue/green publishing and append-mode partitions"
  - "Trace how SwarmPipe publishes, quarantines, rolls back and restores snapshots"
  - "Describe derived datasets, holds and event-driven rebuilds"
  - "Compare static lineage with runtime OpenLineage events and facets"
  - "Use lineage and trusted context for impact analysis and out-of-band change recovery"
---

Publishing is the moment bad data becomes someone else's problem. A batch that stays in processing can be inspected and
fixed; a batch exposed under a stable table name can feed dashboards, reports, models and other agents. Production
systems therefore publish by switching references to immutable versions, not by editing a table in place.

SwarmPipe's warehouse is small enough to run locally, but it uses the same patterns: immutable version tables,
blue/green views, quarantined tables, append-mode partition replacement, snapshots for restore and lineage for impact.
Chapter 6 decided whether a batch is safe. This chapter follows what happens after that decision.

## Immutable versions and blue/green views

:::concept Immutable dataset version
An immutable version is a stored copy of a dataset state that is never updated in place. New data creates a new version;
publishing changes which version consumers read.
:::

In SwarmPipe, every live version is a table named like t__default__sales_daily__v8. The consumer-facing object is a
view named default__sales_daily. Publishing is a view swap. Rollback is another view swap, or, if the current version
was tampered with, a restore from its immutable snapshot.

:::swarmpipe Warehouse primitives
`swarmpipe/data/warehouse.py` documents the design: version table, stable view, quarantine table and read-only analyst
path. The important operation is `swap_view`.

```python
def swap_view(self, tenant: str, dataset: str, table: str) -> None:
    view = self.view_name(tenant, dataset)
    c.execute("BEGIN IMMEDIATE")
    c.execute(f'DROP VIEW IF EXISTS main."{view}"')
    c.execute(f'CREATE VIEW main."{view}" AS SELECT * FROM "{table}"')
    c.execute("COMMIT")
```
:::

:::analogy Railway points
Publishing is like switching railway points. The train keeps asking for `sales_daily`; the operator changes which track
that name points to. If the new track is bad, switch back.
:::

Append-mode datasets add one more rule. `sales_daily` is append-mode and partitioned by `order_date`. A resent partition
replaces the old rows for that partition before deduplication; it does not blindly append a second copy. That prevents
routine re-deliveries from inflating metrics.

:::swarmpipe Publishing service
`swarmpipe/data/publishing.py` stages, publishes, unpublishes, restores and force-publishes versions. Stage writes the
version table and takes a snapshot before any view points at it.

```python
table = Warehouse.table_name(tenant, dataset, version, quarantined=quarantined)
self.wh.write_table(table, full)
self.wh.snapshot(table)
...
"status": "quarantined" if quarantined else "staged",
"checksum": self.wh.checksum(table)
```
:::

Quarantined batches use `q__...` tables. They are preserved for forensics, row samples and governed remediation, but
consumer views do not point to them unless a high-risk `force_publish` action is explicitly approved. Most incidents
should request resend, reprocess with a mapping or roll back, not force publish.

## Derived datasets and holds

SwarmPipe has one derived dataset in `config/consumers.yaml`: `sales_enriched`, built by joining `sales_daily` to
`customers`. When an input publishes, `on_dataset_published` submits a `derive` workflow. The workflow checks inputs,
builds SQL from the declared derived spec and publishes a new immutable derived version.

:::flow Derived propagation
Input publishes | `dataset.published` event
Derive check | inputs published, not held, no high/critical incident
Build SQL | declared in `config/consumers.yaml`
Publish version | same immutable version pattern
OpenLineage event | input datasets -> derived output
:::

A hold stops propagation. The hold-downstream action is a write action held by the Executor agent. It marks downstream
datasets such as `sales_enriched` so `derive` stops with status `held`. The release-hold action reverses it, but release is
approval-gated because releasing a hold can propagate data again.

:::swarmpipe Derive precondition
`dv_check` in `swarmpipe/runtime/workflows.py` stops derived rebuilds when a derived dataset is held or an input has an
open high/critical incident.

```python
if st.get("hold"):
    svc.signals.raise_signal(ctx.tenant, "derive_blocked", name, "info", ...)
    ctx.stop("held", f"{name} is on hold")
...
bad = [i for i in svc.incidents.open_for_dataset(ctx.tenant, inp)
       if i["severity"] in ("high", "critical")]
if bad:
    ctx.stop("blocked", f"input {inp} has an open {bad[0]['severity']} incident")
```
:::

## Lineage and trusted context

Lineage has two layers. **Static lineage** is declared intent: contracts reference other datasets, derived SQL names its
inputs, and the consumer catalog declares which dashboards, reports, models and agents depend on which datasets.
**Runtime lineage** is what actually happened: OpenLineage-style events emitted by workflow runs.

:::concept Trusted context
Trusted context is lineage plus business meaning: owners, source owners, classification, freshness SLAs, consumers,
regulated status and open incidents. It lets agents reason about impact without trusting free-form prompt text.
:::

`swarmpipe/data/lineage.py` seeds static edges from contracts and `config/consumers.yaml`. It emits OpenLineage run
events with `schema`, `dataQualityMetrics`, `dataQualityAssertions`, `columnLineage` and version facets. The **Runs**
tab shows these events; the **Datasets & Lineage** tab shows the graph.

:::swarmpipe Impact analysis
`ContextGraph.impact` walks downstream from a dataset and returns downstream datasets, consumers, owners, regulated
outputs, max criticality and blast radius. Policy uses this for approval escalation.

```python
return {"dataset": dataset,
        "downstream_datasets": datasets,
        "consumers": consumers,
        "owners": owners,
        "regulated": any(c.get("regulated") for c in consumers),
        "max_criticality": crit,
        "blast_radius": len(consumers) + len(datasets)}
```
:::

Impact is not just a pretty graph. If `sales_daily` fails, the blast radius includes `sales_enriched`, the daily revenue
dashboard, GST filing extract and any agent or model that depends on those datasets. The Planner can propose
`hold_downstream`; policy can require approval when regulated outputs are affected.

## Hands-on

Start clean:

```powershell
sp reset --yes
sp init
sp scenarios drop baseline --process
```

Ids, dates and timings vary.

:::lab Tour versions and runtime lineage
1. Open the dashboard and go to **Datasets & Lineage**. Select `sales_daily`. You should see published versions and
   downstream `sales_enriched` plus consumers from `config/consumers.yaml`.

2. Drop a normal day:

   ```powershell
   sp scenarios drop clean_day --process
   sp runs list --workflow derive --limit 5
   ```

   ```output
   dropped ['sales_2026-09-29.csv'] into <your-SwarmPipe-folder>\data\inbox
   | workflow | status    | n |
   | derive   | succeeded | ... |
   ```

3. In **Runs**, open the `ingest_dataset` run for `sales_daily`. Expand **OpenLineage events**. Look for `COMPLETE`
   with schema, data-quality and column-lineage facets. Then open the `derive` run and notice its inputs are
   `sales_daily` and `customers`, while its output is `sales_enriched`.
:::

:::lab Hold downstream, then release
1. Create a serious upstream problem:

   ```powershell
   sp scenarios drop volume_drop --process
   sp status
   ```

   ```output
   | workflow       | status      | n |
   | ingest_dataset | quarantined | 1 |
   ...
   | dataset        | hold |
   | sales_enriched | 1    |
   ```

   The incident proposes and auto-executes `hold_downstream`, so the derived dataset does not rebuild from bad input.

2. Deliver a good replacement:

   ```powershell
   sp scenarios drop clean_day --process
   sp approvals list --status pending
   ```

   ```output
   | kind   | subject                         | risk   |
   | action | release_hold on ['sales_enriched'] | medium |
   ```

3. Approve the release:

   ```powershell
   sp approvals approve <approval_id> --as oncall --comment "Source recovered; release hold"
   sp runs list --workflow derive --limit 5
   ```

   The derive workflow can rebuild again. In **Datasets & Lineage**, `sales_enriched` hold changes back to `0`.
:::

:::lab Detect and restore an out-of-band change
1. Tamper with the published table through the lab-only command:

   ```powershell
   sp scenarios drop oob_tamper --process
   sp incidents list --limit 8
   sp approvals list --status pending
   ```

   ```output
   dropped (chaos/runtime change only) into <your-SwarmPipe-folder>\data\inbox
   admitted 0 file(s); processed in 3.6s
   | status            | severity | dataset     | root_cause               | title                         |
   | awaiting_approval | critical | sales_daily | out_of_band_modification | sales_daily v8 changed outside the pipeline ... |
   ...
   | kind   | subject                         | risk   |
   | action | rollback_dataset on sales_daily | medium |
   ```

   You can also trigger the same tamper directly:

   ```powershell
   sp chaos tamper-warehouse --dataset sales_daily --tenant default
   sp tick --timeout 30
   ```

2. Approve rollback:

   ```powershell
   sp approvals approve <approval_id> --as oncall --comment "Restore the published table from the immutable snapshot"
   sp incidents list --limit 3
   ```

   ```output
   approved rollback_dataset on sales_daily by user:oncall
   | status   | severity | dataset     | root_cause                |
   | resolved | critical | sales_daily | out_of_band_modification  |
   ```

3. The rollback action uses `act_rollback_dataset`. For an older target version it repoints the view; for a tampered
   current version it restores the table from the snapshot and verifies the checksum.
:::

## Break it: edit a published table outside the pipeline

:::breakit Out-of-band tamper
Run the tamper lab above and pause before approval. Predict the blast radius: `sales_daily` feeds
`sales_enriched`, the regulated GST extract and multiple dashboards. The out-of-band detector compares the current
warehouse table checksum with the checksum recorded at publish time. When they differ, it raises a critical incident
and proposes `rollback_dataset`.

What protects downstream is not a model. It is immutable snapshots, recorded checksums, impact analysis and a governed
rollback action.
:::

## Production notes

:::warning Snapshots are only useful if you can prove what they contain
In SwarmPipe, snapshots live in a separate SQLite database and checksums are recorded with dataset versions. In a larger
system, you would use object-lock or WORM storage, retention policies, backup validation and access controls so a
compromised writer cannot alter both live data and its recovery point.
:::

OpenLineage events are runtime evidence, not the whole truth. Static lineage captures intended dependencies before a
run happens. Runtime lineage proves which job produced which output. Trusted context adds owners, SLAs and consumer
criticality. You need all three for safe agentic remediation.

## Quiz

:::quiz
Q: What changes when SwarmPipe publishes a good version?
- [ ] It updates rows inside the old version table
- [x] It writes a new version table, snapshots it and repoints the consumer view
- [ ] It deletes previous versions immediately
> The stable view name is what consumers query; versions remain available for rollback and evidence.

Q: Why are quarantined tables kept?
- [x] For forensics, samples and governed remediation without exposing them to consumers
- [ ] Because SQLite cannot delete tables
- [ ] So dashboards can read failed data by default
> Quarantine preserves evidence while the circuit breaker protects consumers.

Q: What stops `sales_enriched` from rebuilding during a serious upstream incident?
- [ ] The Router refuses derived datasets
- [x] Holds and `derive` preconditions for held or incident-bound inputs
- [ ] The Analyst agent disables SQL
> `dv_check` stops derived rebuilds when the derived dataset is held or an input has an open high/critical incident.

Q: What is the difference between static and runtime lineage?
- [x] Static lineage is declared intent; runtime lineage is emitted by actual workflow runs
- [ ] Static lineage is always more accurate than runtime lineage
- [ ] Runtime lineage exists only in the dashboard
> SwarmPipe uses both: config and contracts seed the graph, while OpenLineage events record what happened.

Q: How is a tampered current version restored?
- [ ] By asking the model to rewrite the table
- [x] By `rollback_dataset`, which can restore the current table from its immutable snapshot and verify checksums
- [ ] By deleting all dataset versions
> The Verifier checks the table checksum against the one recorded when the version was published.
:::

:::takeaways
- Publishing is a controlled pointer switch to an immutable version, not an in-place table edit.
- Append-mode partitions replace resent partitions and deduplicate keys, preventing routine double counting.
- Quarantined tables preserve failed data for evidence without exposing it to consumers.
- Derived datasets rebuild from events, but holds and incident preconditions stop bad propagation.
- Static lineage, OpenLineage runtime events and trusted context together support impact analysis.
- Out-of-band tamper detection depends on recorded checksums, snapshots, rollback actions and verification.
:::
