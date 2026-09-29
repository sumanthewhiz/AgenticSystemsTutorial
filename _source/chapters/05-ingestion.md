---
objectives:
  - "Explain why production ingestion is an admission-control problem, not just a file-read problem"
  - "Compare polling with OS file notifications and describe SwarmPipe's file-stability guard"
  - "Trace one file through `ingest_file`, routing, readers and per-sheet fan-out"
  - "Use duplicate detection, the dead-letter queue and tenant inbox folders safely"
  - "Run ingestion labs for custom CSVs, malformed files, duplicate delivery and tenant drops"
---

A file drop looks simple until it happens at 2:00 AM from a slow network share. The writer is still copying bytes,
the scheduler sees a name in the folder, the reader opens a half-written workbook, and the rest of the pipeline gets a
syntactically valid but incomplete batch. Production ingestion starts by deciding **when a file is safe to admit**.

SwarmPipe treats the watched folder as an event source, but it does not trust the folder blindly. The watcher waits for
stability, hashes content, applies backpressure, moves files into a processing area and only then starts durable work.
The Router and readers decide whether the content is tabular, a document or unsupported; downstream quality checks are
covered in [Chapter 6](06-contracts-and-quality.html).

## The event source is a contract

:::concept Event source
An event source is anything that tells your system "new work is available." In this chapter the source is a local
folder, but the same pattern applies to object storage notifications, message queues, webhooks and CDC logs: detect,
admit, deduplicate, route and record.
:::

Folder-based ingestion is common because it fits old systems: ERP exports, SFTP drops, finance spreadsheets and
vendor reports. The folder is convenient, but it is weakly specified. A file name may appear before the contents are
complete, a sender may redeliver the same file, and a tenant may accidentally drop into the wrong folder.

:::flow Ingestion admission path
Inbox file | appears under `data\inbox`
Stability gate | size and mtime stable for N polls
Admission | hash, tenant, extension and backpressure checks
Durable run | submit `ingest_file`
Route and read | tabular, document or unsupported
Fan-out | one `ingest_dataset` child per table or sheet
Archive, quarantine or DLQ | final location records the outcome
:::

### Polling vs OS notifications

OS notifications feel elegant, but they are not universal. Network drives, USB media and some sync folders can coalesce,
drop or reorder change events. SwarmPipe deliberately polls so the tutorial behaves the same on every laptop and on
messy real-world shares.

:::swarmpipe Watched folder implementation
The watcher lives in `swarmpipe/runtime/watcher.py`. Its module docstring says polling is intentional because it works
on local disks, USB drives and network shares where change notifications are unreliable. `FolderWatcher.poll_once`
records candidate files and admits only those whose size and modification time stay unchanged for
`watcher.stability_polls`.

```python
depth = self.svc.engine.queue_depth()
self.svc.metrics.gauge("queue_depth", depth)
if depth >= w.backpressure_high_watermark:
    self.svc.metrics.gauge("watcher_backpressure", 1)
    return 0
...
stable = prev[2] + 1 if prev and prev[0] == st.st_size and prev[1] == st.st_mtime else 0
if stable >= w.stability_polls:
    ready.append((st.st_mtime, p))
```
:::

File stability matters because "I can see the file" is not the same as "the file is complete." Half-copied CSVs often
parse as short but valid files. Half-copied Excel files often fail with a cryptic parser error. SwarmPipe also honors
ignore globs for temporary names such as producer-side partial files. In industry practice, the strongest pattern is
an atomic rename: write `orders.csv.partial`, then rename to `orders.csv` only after the copy is complete. SwarmPipe
still uses stability polling because not every source follows that discipline.

### Admission control and idempotency

Admission is where SwarmPipe decides whether work should enter the durable engine. The watcher checks the tenant from
the inbox path, rejects unsupported extensions and over-large files, hashes the content with SHA-256 and moves accepted
files into `data\processing\<file_id>`. The hash becomes the idempotency key for delivery: a byte-identical resend is
archived under `archive\duplicates` and counted as `skipped_duplicate`, not processed again.

:::concept Idempotent admission
An operation is idempotent when repeating it has the same effect as doing it once. In ingestion, content hashes prevent
a duplicate delivery from creating duplicate warehouse rows, duplicate incidents or duplicate notifications.
:::

Backpressure is the other half of admission control. If the engine queue is deeper than
`watcher.backpressure_high_watermark`, the watcher leaves files in the inbox and sets the `watcher_backpressure` metric.
That is safer than admitting unlimited work and failing later under memory, database or model pressure. Chapter 24
connects that metric to capacity and cost.

## Routing and readers

Once a file is staged, the `ingest_file` workflow starts. It is intentionally small: `stage -> route -> read -> fanout
-> finalize`. The stage step re-hashes the staged file and checks for duplicate content. The route step uses
`swarmpipe/data/readers.py` `sniff` plus the Router agent to classify files as `tabular`, `document` or `unsupported`.
The Router agent itself is introduced in [Chapter 1](01-llm-to-agent.html); the workflow wiring appears in
[Chapter 2](02-architecture-tour.html).

:::swarmpipe Readers
`swarmpipe/data/readers.py` handles `.csv`, `.tsv`, pipe-delimited `.txt`, `.xlsx` and legacy `.xls`. It sniffs BOMs,
UTF-8, `cp1252`, delimiters, bad lines, workbook containers and multi-sheet spreadsheets. Everything is read as strings
first; `swarmpipe/data/transforms.py` applies types later against a contract.

```python
_DELIMS = [",", "\t", "|", ";"]
...
for enc in ("utf-8", "cp1252"):
    try:
        raw.decode(enc)
        return enc
...
engine = "openpyxl" if sn.extension == ".xlsx" else "xlrd"
sheets = pd.read_excel(path, sheet_name=None, dtype=str, engine=engine, ...)
```
:::

Multi-sheet workbooks are not one dataset. `customers.xlsx` has a `customers` sheet and a `regions` sheet, so
`f_fanout` submits two child `ingest_dataset` runs and waits durably until they finish. Single-table CSV, pipe-delimited
TXT and XLS files create one child. Unsupported content raises a permanent error, and the file goes to the dead-letter
queue.

Tenancy is encoded in the first inbox sub-folder. A file in `data\inbox\acme\sales_...csv` is tenant `acme`; a file
directly under `data\inbox` uses `default`. Dataset views and incidents are then isolated by tenant.

## Hands-on

Before these labs, start from the baseline unless a lab says otherwise:

```powershell
sp reset --yes
sp init
sp scenarios drop baseline --process
```

Ids, dates, timings and costs vary. The output below is trimmed from a real run.

:::lab Create your own CSV and watch onboarding
1. Create a tiny CSV directly in the inbox:

   ```powershell
   @(
     "widget_id,name,price"
     "w-1,Blue widget,12.50"
     "w-2,Red widget,9.99"
   ) | Set-Content -Encoding utf8 .\data\inbox\widgets.csv
   sp tick --timeout 20
   sp approvals list --status pending
   ```

2. Because widgets has no active contract, ingestion pauses at the `onboard` step. This is not an error; it is a
   safe stop before unknown data becomes trusted schema.

   ```output
   admitted 1 file(s); processed in 3.3s
   | workflow       | status  | n |
   | ingest_dataset | waiting | 1 |
   | ingest_file    | waiting | 1 |
   ...
   | id               | kind                | subject    | risk   |
   | apr_...          | contract_onboarding | widgets@v1 | medium |
   ```

3. Open the **Runs** tab and click the waiting `ingest_dataset` run. The current step is `onboard`, and the wait reason
   points to the approval id. Chapter 6 shows how to review and approve the proposed contract.
:::

:::lab Duplicate, malformed and reader scenarios
1. Deliver a normal day, then redeliver the same bytes:

   ```powershell
   sp scenarios drop clean_day --process
   sp scenarios drop duplicate --process
   sp runs list --workflow ingest_file --limit 4
   ```

   ```output
   dropped ['sales_2026-09-29_resent.csv'] into <your-SwarmPipe-folder>\data\inbox
   admitted 1 file(s); processed in 0.0s
   | workflow    | status  |
   | ingest_file | skipped |
   | ingest_file | succeeded |
   ```

2. Drop malformed files and inspect the DLQ:

   ```powershell
   sp scenarios drop malformed --process
   sp dlq list
   ```

   ```output
   dropped ['sales_2026-09-29_corrupt.csv', 'customers_broken.xlsx'] into <your-SwarmPipe-folder>\data\inbox
   | workflow    | status        | n |
   | ingest_file | dead_lettered | 2 |
   ...
   | reason      | error                                      |
   | UNSUPPORTED | unsupported content: not a valid xlsx ... |
   | UNSUPPORTED | unsupported content: NUL bytes in a text file |
   ```

3. Verify reader coverage:

   ```powershell
   sp scenarios drop encoding --process
   sp scenarios drop pipe_txt --process
   ```

   ```output
   dropped ['customers_2026-09-29_cp1252.csv'] into <your-SwarmPipe-folder>\data\inbox
   | ingest_dataset | succeeded | 9 |
   ...
   dropped ['inventory_2026-09-29.txt'] into <your-SwarmPipe-folder>\data\inbox
   | default | inventory | dsv_... | 0 | ...
   ```

4. In the dashboard, use **Runs** to compare the skipped duplicate with the dead-lettered malformed files. Use
   **Incidents** to see how malformed input becomes a triage incident, and **Datasets & Lineage** to confirm duplicate
   delivery did not create a new published dataset version.
:::

:::lab Tenant drop
1. Drop the same clean-day sales file for another tenant:

   ```powershell
   sp scenarios drop clean_day --tenant acme --process
   sp status
   ```

   ```output
   dropped ['sales_2026-09-29.csv'] into <your-SwarmPipe-folder>\data\inbox
   admitted 1 file(s); processed in 9.5s
   | tenant  | dataset     | published_version_id | hold |
   | acme    | sales_daily | dsv_...              | 0    |
   | default | sales_daily | dsv_...              | 0    |
   ```

2. The reader works the same, but the tenant, views, incidents and quotas are separate. Tenant quotas and cost are
   revisited in Chapter 24.
:::

## Break it: deliver the same file twice

:::breakit Duplicate delivery
Run `sp scenarios drop clean_day --process`, then `sp scenarios drop duplicate --process`. Predict what would happen
without a content hash: the append-mode sales dataset would count the same order partition twice, downstream
`sales_enriched` would rebuild from inflated data, and quality checks might diagnose a volume spike instead of a resend.

What you observe instead is an `ingest_file` run with status `skipped`. The stage step raises an informational
`duplicate_file` signal and archives the duplicate. The idempotency guard protects downstream consumers before quality
checks even run.
:::

## Production notes

:::warning Inbox folders are not queues
A folder has no acknowledgement protocol, retry policy or ordering guarantee. SwarmPipe makes it queue-like by moving
files into `processing`, recording a `files` row, using durable workflow checkpoints and preserving bad input in
`data\dlq`. At larger scale you would often replace the folder with object storage plus an event stream, but the same
admission rules still apply.
:::

Use `sp dlq redrive <dlq_id>` only after fixing the cause. Redriving a fake `.xlsx` without replacing the file just
creates another dead letter. The DLQ is for recoverable operator action, not for hiding bad data.

## Quiz

:::quiz
Q: Why does SwarmPipe poll the inbox instead of relying only on OS file notifications?
- [ ] Polling is faster than notifications in all cases
- [x] Polling behaves consistently on local disks, USB drives and network shares where notifications can be unreliable
- [ ] Notifications cannot detect Excel files
> The watcher docstring calls this out directly. Polling plus stability checks is slower but more predictable for messy sources.

Q: What protects downstream data when the same file is delivered twice?
- [ ] The Router agent's confidence score
- [x] The SHA-256 content hash checked in the stage step
- [ ] The dashboard hides duplicate runs
> The duplicate is detected before fan-out. It is archived and the workflow stops as `skipped`.

Q: What does `sp dlq list` show?
- [x] Dead-lettered files with reason, error, path, run id and redrive status
- [ ] Only failed model calls
- [ ] All quarantined dataset rows
> The DLQ is about failed file admission or file workflow failure. Row-level quarantine is shown through checks and dataset versions.

Q: A `.txt` file with consistent `|` separators is routed as what?
- [ ] A document
- [x] Tabular data
- [ ] Unsupported binary
> `readers.py` sniffs `|` as one of the supported delimiters, and the `pipe_txt` scenario publishes `inventory`.
:::

:::takeaways
- Ingestion is admission control: wait for stable files, hash them, move them and only then start durable work.
- Polling is deliberate in SwarmPipe because it is predictable across ordinary and unreliable storage.
- Readers sniff encoding, delimiter and workbook structure, but typing is deferred to contracts in Chapter 6.
- `ingest_file` fans out multi-sheet workbooks into child `ingest_dataset` runs and waits durably.
- Duplicate delivery is skipped by content hash; malformed files go to the DLQ; tenant sub-folders isolate work.
:::
