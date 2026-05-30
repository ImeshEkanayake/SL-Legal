# V2 Pilot Hosting Plan

## Purpose

This document defines the initial hosting plan for a controlled V2 pilot with 3 users.

The pilot plan is intentionally simpler than the final production architecture: one Google Compute Engine VM runs the application services, Postgres, OpenSearch, Qdrant, and Redis, while Google Cloud Storage stores public PDFs, corpus assets, exports, and backups.

The final hosting plan remains a separated architecture with dedicated app, worker, Postgres, search, vector, cache, and object-storage tiers.

## Pilot Scope

Target users:

- 3 initial users.
- Light concurrent usage.
- Controlled lawyer-review workflow.
- Offline or scheduled heavy jobs where possible.

Pilot goals:

- Prove V2 can run against the current corpus and indexes.
- Run the tuned 10-case validation set.
- Validate retrieval, source viewing, reasoning-pack generation, missing-evidence detection, and lawyer-review readiness.
- Measure real memory, CPU, disk, and API usage before moving to the final hosting plan.

Non-goals:

- No public-scale launch.
- No unmanaged production data mutation.
- No raw data upload to GitHub.
- No database migration outside reviewed migration phases.
- No final legal advice language.

## Current Measured Footprint

Measured from the local V2 stack:

| Component | Current Size |
| --- | ---: |
| MinIO object corpus storage | 183.7 GB |
| Postgres Docker volume | 26 GB |
| Postgres logical database | 23 GB |
| Qdrant vector store | 10.5 GB |
| OpenSearch index store | 7.1 GB |
| Redis | negligible |

Approximate live persistent footprint:

```text
227 GB
```

The pilot must not size only for Postgres. The object corpus and derived indexes drive the real storage requirement.

## Recommended Pilot Architecture

```text
Internet
  |
  v
HTTPS endpoint / reverse proxy
  |
  v
Single Compute Engine VM
  - Next.js frontend
  - Python API
  - background worker
  - Postgres
  - OpenSearch
  - Qdrant
  - Redis
  |
  v
Google Cloud Storage
  - public PDFs / corpus assets
  - backups
  - exports
  - snapshots
```

Only the web entrypoint should be public. Postgres, OpenSearch, Qdrant, Redis, and internal service ports must stay private.

## Recommended VM

Preferred pilot VM:

```text
n4-standard-4
4 vCPU
16 GB RAM
```

This is the lowest practical pilot size for the current stack. It is acceptable for 3 light users, but it should be treated as a constrained environment.

Comfortable pilot VM:

```text
n4-standard-8
8 vCPU
32 GB RAM
```

Use this if indexing, full-corpus searches, or simultaneous reasoning-pack generation feels slow on the smaller VM.

## Disk Plan

Recommended pilot disk layout:

| Disk | Size | Use |
| --- | ---: | --- |
| Boot disk | 80-100 GB | OS, Docker, app code, logs |
| Data disk | 500 GB minimum | Postgres, OpenSearch, Qdrant, Redis local volumes |
| Data disk preferred | 750 GB-1 TB | More headroom for index growth and maintenance |
| Cloud Storage | 500 GB-1 TB planned | PDFs, corpus assets, backups, exports, snapshots |

Minimum workable storage:

```text
100 GB boot disk
500 GB balanced data disk
Cloud Storage bucket for PDFs and backups
```

Preferred storage:

```text
100 GB boot disk
1 TB balanced data disk
Cloud Storage bucket with lifecycle policy
```

Google Drive must not be used for Postgres, OpenSearch, or Qdrant data files. These services require block storage with low-latency random reads and writes. Google Drive can be used only for manual sharing, not as database or index storage.

## Estimated Monthly Cost

Reduced 3-user pilot estimate:

| Item | Estimate |
| --- | ---: |
| `n4-standard-4` VM | 138-150 USD/month |
| 100 GB boot disk | 8-10 USD/month |
| 500 GB balanced data disk | 40-45 USD/month |
| Cloud Storage PDFs and backups | 20-50 USD/month |
| Static IP and light network usage | 5-20 USD/month |

Expected reduced pilot total:

```text
210-275 USD/month
```

Safer budget:

```text
300 USD/month
```

If using a 1 TB data disk instead of 500 GB, add approximately:

```text
40-45 USD/month
```

This estimate excludes:

- OpenAI or Azure OpenAI API usage.
- Heavy public egress.
- Load balancers.
- Cloud Armor.
- Managed monitoring/logging overages.
- Domain, email, or support costs.

## Container Resource Targets

For `n4-standard-4`, start conservatively:

| Service | Memory Target |
| --- | ---: |
| OpenSearch | 4 GB container limit, 2-3 GB heap |
| Qdrant | 3-4 GB |
| Postgres | 3-4 GB |
| Python API and workers | 2-3 GB |
| Next.js frontend | 1 GB |
| Redis | 256-512 MB |
| OS and Docker headroom | 2-3 GB |

For `n4-standard-8`, increase:

| Service | Memory Target |
| --- | ---: |
| OpenSearch | 6-8 GB container limit, 4 GB heap |
| Qdrant | 6-8 GB |
| Postgres | 6-8 GB |
| Python API and workers | 4-6 GB |
| Next.js frontend | 1-2 GB |
| Redis | 512 MB-1 GB |
| OS and Docker headroom | 4 GB |

## Required Host Settings

OpenSearch requires:

```bash
sudo sysctl -w vm.max_map_count=262144
```

Persist it:

```text
vm.max_map_count=262144
```

in:

```text
/etc/sysctl.conf
```

Use Docker restart policies or systemd units so services restart after VM reboot.

## Security Rules

Expose only:

- HTTPS web entrypoint.
- SSH restricted to trusted IPs or IAP.

Do not expose publicly:

- Postgres `5432/5433`.
- OpenSearch `9200/9600`.
- Qdrant `6333/6334`.
- Redis `6379/6380`.
- MinIO console or internal object endpoints unless deliberately protected.

Required controls:

- Use real secrets, not development defaults.
- Store secrets in Secret Manager or locked VM environment files.
- Do not write secrets into logs.
- Use HTTPS.
- Keep signed request headers and session cookies out of reports.
- Keep lawyer-review requirement visible in generated outputs.

## Backup Plan

Backups go to Google Cloud Storage.

Minimum backup schedule:

- Daily Postgres logical backup.
- Daily Postgres physical or volume snapshot if practical.
- Weekly OpenSearch snapshot.
- Weekly Qdrant snapshot.
- Daily app config export without secrets.
- Daily corpus manifest/checksum export.

Retention:

- Daily backups: 14-30 days.
- Weekly backups: 8-12 weeks.
- Monthly backups: 6-12 months if budget allows.

Backup validation:

- Restore Postgres to a separate test database at least once before pilot sign-off.
- Verify OpenSearch and Qdrant snapshots can be listed and downloaded.
- Keep raw PDFs and derived text assets in Cloud Storage, not only on the VM disk.

## Operating Rules For The Small VM

Because the reduced pilot VM is constrained:

- Run ingestion, OCR, index rebuilds, and full-corpus backfills off-hours.
- Limit simultaneous heavy reasoning-pack jobs.
- Prefer one heavy validation run at a time.
- Watch disk usage before and after index rebuilds.
- Keep Docker image/build cache pruned.
- Keep large logs out of Git and rotate them.

## Monitoring

Track at minimum:

- VM CPU.
- VM memory.
- Data disk used percent.
- Postgres size and table growth.
- OpenSearch heap and disk.
- Qdrant memory and disk.
- API error rate.
- Retrieval latency.
- Source viewer latency.
- Citation validation failures.
- Review queue latency.

Alert thresholds for pilot:

- Data disk above 75 percent: review immediately.
- Data disk above 85 percent: stop ingestion/index rebuilds.
- VM memory above 85 percent for 15 minutes: reduce worker concurrency or upgrade VM.
- OpenSearch heap pressure sustained above safe operating range: reduce load or upgrade VM.
- Postgres backup failure: block pilot sign-off.

## 10-Case Validation Plan

After the pilot VM is deployed and the corpus/indexes are restored:

1. Confirm app health and signed API smoke checks.
2. Confirm Postgres, OpenSearch, Qdrant, Redis, and Cloud Storage access.
3. Confirm source viewer can fetch PDFs or cached page evidence.
4. Run the tuned 10-case validation set.
5. Inspect supportive evidence, adverse evidence, authority citation behavior, for/against reasoning quality, missing evidence, and lawyer-review readiness.
6. Record resource usage during the run.
7. Decide whether the pilot can continue on `n4-standard-4` or should move to `n4-standard-8`.

Canonical existing 10-case validation assets:

- `rag/evals/two_stage_tuned_cases.json`
- `scripts/run_two_stage_recall_precision_checks.py`
- `scripts/run_phase27_full_case_validation.py`
- `Docs/v2_phase_27_full_case_validation_contract.md`

## Upgrade Triggers

Move from `n4-standard-4` to `n4-standard-8` if any of these occur:

- Search or reasoning feels slow for the 3 users.
- Full 10-case validation causes memory pressure.
- OpenSearch or Qdrant is repeatedly starved.
- Postgres cache hit rate or query latency becomes poor.
- The team needs concurrent validation plus normal pilot usage.

Move to the final separated hosting plan if any of these occur:

- More than 3-5 regular users.
- Formal production SLA requirement.
- Frequent ingestion or index rebuilds.
- Larger corpus growth.
- Need for independent Postgres/search/vector scaling.
- Need for stronger isolation, backup, and incident recovery.

## Final Hosting Plan Target

The final plan remains:

- App/frontend tier.
- Background worker tier.
- Managed or dedicated Postgres.
- Dedicated OpenSearch.
- Dedicated Qdrant.
- Redis cache/queue.
- Managed object storage.
- Separate backup and monitoring controls.

Target final baseline:

```text
16-20 vCPU total
56-72 GB RAM total
600 GB minimum live storage
1 TB comfortable live storage
1-2 TB planned backup/object retention
```

The pilot is a cost-controlled bridge to collect real usage evidence before paying for that final architecture.
