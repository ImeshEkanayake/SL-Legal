# Sri Lankan Legal AI Data Requirements and Missing-Data Register, 1948-Present

**Purpose:** Define the complete legal-data corpus required for a production-grade Sri Lankan lawyer-assistance system, starting from the 1948 independence period and tracking all available, missing, incomplete, licensed, archival, and hard-to-acquire material.

**Important framing:** This document is not an MVP scope. It is the product corpus blueprint. Extraction can happen in phases, but the data model must be capable of representing the full legal record, missing-data status, source reliability, provenance, and legal authority from the start.

**Date created:** 2026-05-21

---

## 1. Corpus Principle

The system should not simply collect documents. It should build a traceable legal data system.

```text
Every legal item must have:
- Source identity
- Source reliability tier
- Legal authority type
- Jurisdiction
- Date or date range
- Language
- Version / amendment status
- Acquisition status
- Licence status
- Extraction status
- OCR / text quality score
- Missing-data status, if incomplete
- Citation / reference fields
- Relationship to other legal items
```

No legal strategy, argument generation, or case analysis should use untracked data. If a source is missing, incomplete, unverified, or outside the retrieved Legal Research Pack, the system must show that limitation.

Language acquisition policy:

```text
- Prefer official English documents wherever English is available.
- Do not download Sinhala/Tamil duplicates for the same legal item when a complete official English copy exists.
- Keep Sinhala/Tamil copies only where English is unavailable, where the language text has independent legal importance, or where it is needed as gap evidence.
- Record language choice in the manifest so later retrieval can explain whether a non-English official text was skipped or retained.
```

---

## 2. Time Coverage

The core collection period is 1948-present.

```text
Primary coverage:
- 1948-present legal instruments, cases, gazettes, parliamentary material, and court materials.

Continuity coverage:
- Pre-1948 Ordinances, codes, and legal materials that remained in force after independence.
- Colonial-era case law still cited in Sri Lankan law.
- Privy Council decisions affecting Ceylon / Sri Lanka before appeals were abolished.
```

The system must not ignore pre-1948 law where it remains legally relevant. Many core legal instruments, including criminal, evidence, procedure, land, succession, and personal-law materials, may have origins before 1948 but continue to matter after 1948.

---

## 3. Constitutional Eras To Track

```text
Era 1: 1948-1972
- Dominion of Ceylon / Soulbury constitutional framework
- Independence-period legislation
- Appeals and constitutional material from the Ceylon period

Era 2: 1972-1978
- First Republican Constitution
- National State Assembly period
- Laws enacted under the 1972 constitutional order

Era 3: 1978-present
- Second Republican Constitution
- Constitutional amendments
- Supreme Court constitutional jurisdiction
- Special determinations on Bills
- Fundamental rights jurisprudence
- Provincial Council framework after the Thirteenth Amendment
```

Required constitutional records:

```text
- Constitutional texts
- Amendments
- Bills to amend the Constitution
- Supreme Court special determinations
- Referendum materials, where applicable
- Gazette publications of constitutional instruments
- Parliamentary debates on constitutional changes
- Transitional provisions
- Repeal / replacement relationships
- Official Sinhala, Tamil, and English texts where available
```

---

## 4. Master Data Categories

### 4.1 Constitutional and Foundational Law

```text
Collect:
- 1948 constitutional framework and related independence instruments
- 1972 Constitution
- 1978 Constitution
- All constitutional amendments
- Proposed constitutional amendment Bills
- Supreme Court special determinations on constitutional Bills
- Referendum-related legal materials
- Transitional provisions and repeals

Track:
- Instrument name
- Enactment / effective date
- Repealed or current status
- Language versions
- Source reliability
- Relationship to later amendments
- Related judgments and special determinations
```

### 4.2 Acts, Ordinances, Laws, and Amendments

```text
Collect:
- Acts of Parliament from 1948-present
- Laws enacted during the National State Assembly period
- Pre-1948 Ordinances still in force
- Amendment Acts
- Repealing Acts
- Revival / validation Acts
- Commencement orders and appointed-date notices
- Consolidated versions, where official or licensed
- Chronological and alphabetical indexes

Track:
- Act / Ordinance / Law number
- Year
- Short title
- Long title
- Date of certification / assent
- Commencement date
- Amended provisions
- Repealed provisions
- Current-force status
- Related gazettes
- Related Bills
- Related cases
```

### 4.3 Bills and Legislative Process Materials

```text
Collect:
- Government Bills
- Private Members' Bills
- Bill gazettes
- Sectoral Oversight Committee reports
- Legislative Standing Committee reports
- Committee-stage amendments
- Supreme Court special determinations
- Speaker's certificate / final Act links
- Hansard debates on Bills

Track:
- Bill number / gazette reference
- Date published in Gazette
- First Reading
- Second Reading
- Committee stage
- Third Reading
- Supreme Court petition / determination status
- Whether enacted, withdrawn, rejected, lapsed, or amended
```

Parliament states that the Bills Office processes Bills from introduction through final Act printing and maintains Bills and Acts registers. Parliament also explains the Bill process, including gazette publication, readings, committee stage, and Speaker's certificate. See the source notes at the end of this document.

### 4.4 Gazettes and Extraordinary Gazettes

```text
Collect:
- Ordinary Gazettes
- Extraordinary Gazettes
- Gazette parts and sections
- Regulations
- Rules
- Orders
- Notices
- Appointments
- Commencement notices
- Statutory instruments
- Ministerial and departmental notices
- Election-related notices
- Land acquisition notices
- Public service notices
- Court and tribunal notices

Track:
- Gazette number
- Date
- Part / section
- Language
- Issuing authority
- Legal authority cited
- Instrument type
- Related Act / provision
- Effective date
- Revocation / amendment relationship
- PDF availability
- OCR quality
```

Known availability issue:

```text
The live Department of Government Printing site exposes quick links for Gazettes, Extra-Gazettes, Acts, Bills, Forms, and Notices, but the home page was under construction when checked on 2026-05-21. The Gazette archive page showed online year links from 2004 onward. Older gazettes must be treated as an archival acquisition task unless another verified source is found.
```

### 4.5 Case Law

```text
Collect:
- Privy Council decisions affecting Ceylon / Sri Lanka
- Supreme Court judgments
- Supreme Court special determinations
- Court of Appeal judgments and orders
- Court of Criminal Appeal / historical appellate material, where relevant
- High Court judgments
- Commercial High Court judgments
- Provincial High Court judgments
- District Court decisions, where available
- Magistrates' Court decisions, where available
- Labour Tribunal decisions
- Industrial Court / arbitration decisions
- Tax Appeal Commission and revenue decisions
- Administrative tribunal decisions
- Election petition decisions
- Fundamental rights cases
- Writ cases
- Reported and unreported judgments

Track:
- Case name
- Court
- Case number
- Date
- Bench / judge
- Parties
- Counsel, if available
- Procedural posture
- Subject area
- Statutes considered
- Cases cited
- Ratio / holding
- Final order
- Later treatment
- Report citation
- Neutral citation, if available
- PDF / source URL
- Source reliability and completeness
```

Known availability issue:

```text
The Supreme Court website provides a judgments menu with recent year categories and special determinations. The Court of Appeal website links to Judgments and Orders. Historical, lower-court, and unreported materials are likely incomplete online and must be tracked as missing, licensed, archival, or partnership-dependent.
```

### 4.6 Law Reports and Report Series

```text
Collect:
- New Law Reports
- Sri Lanka Law Reports
- other official or semi-official reports
- commercial report series, if licensed
- subject-specific reports, if licensed
- headnotes, only where licence permits

Track:
- Report series
- Volume
- Year
- Page
- Case name
- Court
- Judgment date
- Reporter citation
- Whether full judgment is available
- Whether headnote is available
- Licence status
```

### 4.7 Procedural Law and Court Rules

```text
Collect:
- Civil Procedure Code
- Code of Criminal Procedure
- Evidence Ordinance
- Judicature Act and amendments
- Supreme Court Rules
- Court of Appeal Rules
- High Court Rules
- Commercial High Court Rules
- Labour Tribunal procedure
- Bail-related law and rules
- Appeal, revision, writ, FR, and leave-to-appeal procedure
- Standing Orders of Parliament where relevant to constitutional and legislative process

Track:
- Current version
- Historical versions
- Amendments
- Commencement
- Related cases
- Related forms
- Deadlines and limitation periods
```

### 4.8 Provincial Council, Local Authority, and Subnational Law

```text
Collect:
- Provincial Council statutes
- Provincial regulations
- Provincial gazettes
- Municipal by-laws
- Urban Council by-laws
- Pradeshiya Sabha by-laws
- local government notices

Track:
- Province / local authority
- Subject matter
- Enabling Act or constitutional source
- Gazette publication
- Effective date
- Current status
- Language availability
```

### 4.9 Administrative, Executive, and Regulatory Material

```text
Collect:
- Ministry circulars
- Judicial Service Commission circulars
- Attorney General's Department material, where public or licensed
- Police circulars and forms
- Immigration, tax, customs, land, labour, companies, banking, procurement, and public administration circulars
- Departmental guidelines
- Regulatory authority directions
- practice notes and registry notices

Track:
- Issuing body
- Legal authority
- Date issued
- Effective date
- Revoked / amended status
- Binding or guidance status
- Public / restricted status
```

### 4.10 Parliamentary and Legislative History

```text
Collect:
- Hansard debates
- corrected Hansard volumes
- parliamentary questions
- order papers
- order books
- committee reports
- select committee reports
- sectoral oversight committee reports
- papers presented
- votes and proceedings
- minutes of Parliament
- constitutional debates
- budget speeches and appropriation debates

Track:
- Sitting date
- Parliament / session
- speaker / member
- subject
- related Bill or Act
- language
- corrected / uncorrected status
- PDF / text availability
- OCR quality
```

The Parliament Hansard Department describes its role as preparing printed Parliamentary Proceedings and verbatim reports of Parliament and committee meetings, with corrected versions later proofread and bound with indexes.

Current acquisition note:

```text
The official Parliament English Hansard listing and corrected-volume listing are now treated as active source tracks. The initial downloader prefers English PDFs and writes both manifest rows and a hansard_registry table. Online daily Hansard coverage appears partial and starts well after 1948; corrected online volumes also appear partial. Pre-online Hansards, committee proceedings, and indexes remain archival acquisition tasks.
```

### 4.11 Treaties, Conventions, and International Materials

```text
Collect:
- International conventions ratified by Sri Lanka
- bilateral and regional agreements
- mutual legal assistance agreements
- extradition treaties
- human-rights treaty materials
- UN treaty body materials involving Sri Lanka
- local implementing Acts and regulations

Track:
- Treaty name
- Signature date
- Ratification / accession date
- Entry into force
- Reservations / declarations
- Domestic implementing law
- Related cases
```

### 4.12 Legal Profession, Court Administration, and Practice Material

```text
Collect:
- court forms
- filing rules
- registry notices
- certified-copy procedures
- court calendars and holidays
- professional conduct materials
- Bar Association material, if licensed
- Law College and Judges' Institute materials, if licensed or public

Track:
- Source
- practice area
- court level
- current / obsolete status
- public / restricted status
- licence status
```

### 4.13 User Case Files and Firm Knowledge

```text
Collect, only with proper permission:
- client facts
- pleadings
- affidavits
- witness statements
- contracts
- correspondence
- police records
- medical reports
- expert reports
- prior orders
- written submissions
- internal research notes
- sample pleadings

Track:
- tenant / firm
- matter
- confidentiality level
- privilege status
- permission for indexing
- permission for training, normally false
- retention / deletion rules
- source document hash
```

Firm and client data must never be treated as legal authority unless supported by primary legal sources.

---

## 5. Source Reliability Tiers

```text
Tier A: Official source
- Parliament
- Department of Government Printing
- Supreme Court
- Court of Appeal
- Ministry / department / regulator official sites
- official gazette publications

Tier B: Officially connected or government-hosted legal portal
- LawNet / Ministry of Justice legal portal
- official consolidated legislative enactments where provenance is clear

Tier C: Licensed legal database or publisher
- commercial law-report database
- paid consolidated legislation
- licensed textbooks or practice guides

Tier D: Archival source
- National Archives
- libraries
- scanned historical reports
- bound volumes
- microfilm or physical gazettes

Tier E: Lawyer-uploaded or firm source
- matter documents
- internal examples
- submissions
- research notes

Tier F: Unverified web source
- blogs
- scraped summaries
- news reports
- unofficial reposts
```

Use Tier F only for discovery leads. It must not support legal conclusions.

---

## 6. Initial Source Register

| Source ID | Source | Data Type | Current Online Signal | Reliability Tier | Initial Status | Gap Risk |
|---|---|---|---|---|---|---|
| PARL_ACTS | Parliament Acts listing | Acts | Year filters include 1948-present and current Acts with view/download links | A | Start extraction | Need verify PDF coverage by year and language |
| PARL_BILLS | Parliament Acts and Bills | Bills and Act/Bill metadata | Official page defines Acts and Bills and links to all Acts / all Bills | A | Start extraction | Need map Bills to final Acts and special determinations |
| PARL_HANSARD_DAILY | Parliament Hansards listing | Daily Hansard PDFs | Official English listing exposes downloadable PDFs | A | Active extraction | Online coverage is partial; historical records before visible online years remain archival |
| PARL_HANSARD_VOLUMES | Parliament Corrected Hansards (Volumes) | Corrected bound-volume PDFs | Official English listing exposes downloadable corrected volumes | A | Active extraction | Corrected volume coverage is partial; indexes and committee material remain separate gaps |
| GOV_PRINT | Department of Government Printing | Gazettes, Extra-Gazettes, Acts, Bills, Forms, Notices | Site exposes quick links but home page was under construction on 2026-05-21 | A | Source discovery | Need robust access paths and fallback archival process |
| GOV_GAZETTES | Gazette Archive | Gazettes | Archive page shows online year links from 2004 onward | A | Start extraction for visible years | Pre-2004 gazettes likely archival/missing |
| SC_OFFICIAL | Supreme Court | Judgments, special determinations, court diary | Website lists Judgments, years 2020-2026, and Special Determinations | A | Start extraction | Earlier judgments require reports, archives, or other sources |
| CA_OFFICIAL | Court of Appeal | Judgments, orders, daily lists | Site map links to Judgments and Orders | A | Start extraction | Historical coverage and download quality need mapping |
| LAWNET_MOJ | LawNet / Ministry of Justice | Legislation, reports, core laws, links | Portal lists legislative enactments, consolidated legislation, core legislation, NLR, SLR, SC and CA judgments | B | Source discovery and verification | Links may redirect; provenance and completeness must be validated |
| NAT_ARCHIVES | National Archives / libraries | Historical gazettes, Hansard, ordinances, reports | Required for older physical or scanned holdings | D | Acquisition planning | Access may require manual request, scanning, or partnership |
| LICENSED_DB | Licensed legal databases | Consolidated law, reported cases, annotations | Potentially needed for complete coverage | C | Partnership planning | Licence restrictions and cost |
| LAW_FIRM_UPLOADS | User / law firm uploads | Matter files and internal work product | Private uploads only | E | Product workflow source | Confidentiality and privilege constraints |

---

## 7. Required Master Tables

### 7.1 Source Registry

```json
{
  "source_id": "GOV_GAZETTES",
  "source_name": "Department of Government Printing Gazette Archive",
  "source_url": "https://www.documents.gov.lk/view/gazettes/find_gazette.html",
  "source_owner": "Department of Government Printing",
  "reliability_tier": "A",
  "legal_authority_type": "official_publication",
  "jurisdiction": "Sri Lanka",
  "languages": ["Sinhala", "Tamil", "English"],
  "coverage_start": "2004-01-01",
  "coverage_end": null,
  "coverage_confidence": "partial_until_verified",
  "licence_status": "to_review",
  "access_method": "web_archive",
  "refresh_frequency": "daily_or_weekly",
  "known_gaps": ["pre_2004_online_archive"],
  "notes": "Older gazettes require archival acquisition plan."
}
```

### 7.2 Document Manifest

```json
{
  "document_id": "doc_000001",
  "source_id": "PARL_ACTS",
  "document_type": "Act",
  "title": "Ceylon Citizenship Act",
  "year": 1948,
  "number": "18/1948",
  "language": "English",
  "source_url": null,
  "downloaded_at": null,
  "file_path": null,
  "file_hash": null,
  "acquisition_status": "missing_or_to_extract",
  "extraction_status": "not_started",
  "ocr_required": null,
  "text_quality_score": null,
  "legal_status": "to_verify",
  "missing_reason": "source_url_not_yet_verified",
  "next_action": "locate official PDF or archival scan"
}
```

### 7.3 Legal Instrument Registry

```json
{
  "instrument_id": "act_1948_18",
  "instrument_type": "Act",
  "short_title": "Ceylon Citizenship Act",
  "number": "18",
  "year": "1948",
  "certified_date": null,
  "commencement_date": null,
  "current_status": "to_verify",
  "amends": [],
  "amended_by": [],
  "repeals": [],
  "repealed_by": [],
  "related_bills": [],
  "related_gazettes": [],
  "related_cases": [],
  "versions": []
}
```

### 7.4 Case Registry

```json
{
  "case_id": "case_to_assign",
  "case_name": null,
  "court": "Supreme Court",
  "case_number": null,
  "decision_date": null,
  "report_citation": null,
  "neutral_citation": null,
  "source_id": "SC_OFFICIAL",
  "source_url": null,
  "download_status": "not_started",
  "reported_status": "to_verify",
  "later_treatment_status": "unknown",
  "statutes_considered": [],
  "cases_cited": [],
  "legal_issues": []
}
```

### 7.5 Missing-Data Register

```json
{
  "missing_id": "missing_000001",
  "data_category": "Gazette",
  "expected_coverage": "1948-2003",
  "known_available_coverage": "2004-present online archive visible",
  "missing_description": "Older official gazettes not yet located in machine-downloadable official archive.",
  "legal_importance": "high",
  "risk_if_missing": "Cannot verify commencement notices, regulations, appointments, orders, and delegated legislation.",
  "probable_source": "National Archives / Government Printing / libraries / licensed collections",
  "next_action": "Contact official source or locate archival digitisation partner.",
  "owner": "Corpus lead",
  "status": "open",
  "last_checked": "2026-05-21"
}
```

### 7.6 Extraction Run Log

```json
{
  "run_id": "extract_000001",
  "source_id": "PARL_ACTS",
  "run_type": "metadata_discovery",
  "started_at": "2026-05-21T00:00:00Z",
  "ended_at": null,
  "documents_found": 0,
  "documents_downloaded": 0,
  "errors": [],
  "new_missing_items": [],
  "notes": "Initial source discovery."
}
```

---

## 8. Initial Missing-Data Register

| ID | Category | Expected Coverage | Known Online Coverage / Signal | Missing or Unverified Data | Priority | Next Action |
|---|---|---:|---|---|---|---|
| M001 | Ordinary Gazettes | 1948-present | Online archive visibly lists 2004-present | 1948-2003 gazettes | Critical | Find official archival source, library holdings, or scanning partner |
| M002 | Extraordinary Gazettes | 1948-present | Department site exposes Extra-Gazettes link | Full historical coverage unverified | Critical | Map available years and identify gaps |
| M003 | Acts | 1948-present plus still-in-force pre-1948 Ordinances | Parliament Acts listing includes 1948-present year filters | PDF availability, languages, and completeness by year unverified | Critical | Crawl metadata, compare against chronological index |
| M004 | Bills | 1948-present | Parliament Bills pages exist for current process | Historical Bills and failed/lapsed Bills likely incomplete | High | Map Bills by year and link to Acts / Hansard / determinations |
| M005 | Supreme Court judgments | 1948-present | Supreme Court site shows recent judgment years and special determinations | Pre-2020 official site coverage and older reports | Critical | Extract current site, then acquire reports / archives |
| M006 | Court of Appeal judgments/orders | 1971-present | Court of Appeal site links to Judgments and Orders | Historical and unreported coverage unknown | Critical | Extract current site, then map older report series |
| M007 | Privy Council decisions | 1948-1972 relevance, plus older still-cited decisions | Not in current Sri Lankan official court sites | Full Ceylon/Sri Lanka Privy Council corpus | High | Identify public-domain sources and report citations |
| M008 | High Court and lower-court decisions | 1948-present | No comprehensive public signal found in initial pass | Most lower-court decisions | High | Treat as partnership/licensed/law-firm upload corpus |
| M009 | Hansard | 1948-present | Hansard Department confirms proceedings and committee reporting | Historical volume download coverage and OCR quality | High | Locate online volumes and archival holdings |
| M010 | Law reports | 1948-present | LawNet links to NLR and SLR | Completeness, licence, and PDF/text availability | Critical | Verify LawNet links and licensed report options |
| M011 | Provincial Council statutes | 1987-present | LawNet links to Provincial Council and Local Authorities Statutes | Completeness and province-level gazette coverage | High | Build province-by-province source map |
| M012 | Administrative circulars | 1948-present | Distributed across ministries/departments | Fragmented and inconsistent archives | Medium | Build per-agency source registry |
| M013 | Sinhala and Tamil versions | 1948-present | Some official sources expose multilingual material | Language completeness unknown | Critical | Track language availability per document |
| M014 | Commencement notices | 1948-present | Usually in gazettes | Not linked reliably to Acts yet | Critical | Extract gazette notices and link to legal instruments |
| M015 | Repeal/amendment graph | 1948-present | Partly inferable from Acts/consolidations | Full machine-readable amendment graph missing | Critical | Build amendment parser plus lawyer verification workflow |

---

## 9. Extraction Workflow

```text
1. Source discovery
   Identify source, owner, coverage, format, licence, and reliability tier.

2. Metadata crawl
   Extract document title, date, number, year, language, URL, source page, and file type.

3. Manifest creation
   Create one manifest row per expected document, including missing rows.

4. Download / acquisition
   Download public files where permitted; log manual, archival, or partnership tasks where not.

5. Hash and store
   Store raw file with immutable hash and source metadata.

6. OCR / text extraction
   Extract text with page, paragraph, language, and confidence data.

7. Legal segmentation
   Segment Acts, gazettes, judgments, Bills, and procedural material differently.

8. Entity and citation extraction
   Extract Act numbers, case citations, sections, parties, courts, judges, dates, and gazette references.

9. Version and relationship building
   Build amendment, repeal, commencement, citation, and later-treatment links.

10. Quality review
   Send low-confidence OCR, metadata conflicts, missing citations, and authority conflicts to review.

11. Missing-data update
   Any expected item that cannot be acquired becomes an explicit missing-data record.

12. Research-pack eligibility
   Only verified, indexed, cited, and source-tracked documents can enter a Legal Research Pack.
```

---

## 10. Proposed Storage Layout

```text
data/
├── raw/
│   ├── official/
│   │   ├── parliament/
│   │   ├── government_printing/
│   │   ├── supreme_court/
│   │   ├── court_of_appeal/
│   │   └── ministries_and_regulators/
│   ├── law_reports/
│   ├── archives/
│   ├── licensed/
│   └── firm_uploads/
│
├── extracted/
│   ├── text/
│   ├── ocr/
│   ├── layout/
│   ├── tables/
│   └── citations/
│
├── manifests/
│   ├── source_registry.csv
│   ├── document_manifest.csv
│   ├── legal_instrument_registry.csv
│   ├── case_registry.csv
│   ├── gazette_registry.csv
│   ├── missing_data_register.csv
│   └── extraction_run_log.csv
│
└── indexes/
    ├── search/
    ├── vector/
    └── graph/
```

---

## 11. Corpus Completion Rules

The corpus should be considered production-usable only when:

```text
- Every known source has a source-registry row.
- Every expected legal item has either a document row or a missing-data row.
- Every downloaded file has a hash and source URL or acquisition record.
- Every legal instrument has amendment and repeal status marked as verified, partial, or unknown.
- Every judgment has court, date, case number or citation, and source reliability status.
- Every gazette issue has date, number, language, and extraction status.
- Every missing data point has an owner, next action, and last-checked date.
- Every Legal Research Pack can prove which documents were available and which were missing.
```

The goal is not to pretend the corpus is complete. The goal is to know exactly what is complete, what is partial, what is missing, and what legal risk the missing material creates.

---

## 12. First Extraction Priorities

This is a product build, but extraction still needs an ordered sequence.

```text
Priority 1: Master registries
- source_registry
- document_manifest
- missing_data_register
- extraction_run_log

Priority 2: Official legislation and constitutional data
- Constitution and amendments
- Acts 1948-present
- still-in-force pre-1948 Ordinances
- core procedural laws
- commencement and repeal data

Priority 3: Gazettes and subsidiary legislation
- gazettes visible online
- extraordinary gazettes visible online
- regulations, orders, rules, notices
- older gazette acquisition plan

Priority 4: Appellate case law
- Supreme Court judgments and special determinations
- Court of Appeal judgments and orders
- law reports
- Privy Council / historical appellate material

Priority 5: Legislative history
- Bills
- Hansard daily PDFs
- corrected Hansard volumes
- committee reports and proceedings
- order papers and parliamentary records
- indexes and archival pre-online volumes

Priority 6: Hard-to-acquire data
- lower-court decisions
- tribunal decisions
- provincial and local materials
- administrative circulars
- licensed commentary and practice material
```

---

## 13. Source Notes Checked On 2026-05-21

1. Parliament Acts listing shows Parliament/session filters and year filters including 1948-present, with current Acts offering view/download links: https://www.parliament.lk/en/business-of-parliament/acts-listing
2. Parliament Acts and Bills page defines Acts and Bills and links to all Acts and all Bills: https://www.parliament.lk/en/business-of-parliament/acts-bills?tab=bills
3. Parliament Bills Office describes processing Bills from introduction through final Act printing and maintaining Bills and Acts registers: https://www.parliament.lk/en/secretariat/department/legislative-services/50
4. Parliament Government Bills page describes gazette publication, readings, committee stage, and Speaker's certificate: https://www.parliament.lk/en/learn/how-parliament-works/government-bills?showall=&start=1
5. Parliament Hansard Department describes preparation of Parliamentary Proceedings and verbatim reports of House and committee proceedings: https://beta.parliament.lk/en/secretariat/department/handsard
6. Department of Government Printing home page exposes quick links for Gazettes, Extra-Gazettes, Acts, Bills, Forms, and Notices, but was under construction when checked: https://www.documents.gov.lk/
7. Department of Government Printing Gazette Archive page showed year links from 2004 onward when checked: https://www.documents.gov.lk/view/gazettes/find_gazette.html
8. Supreme Court site lists Judgments, recent judgment years, and Special Determinations: https://supremecourt.lk/
9. Court of Appeal site map links to Judgments and Orders and describes the Court as second most senior court, with appeals to the Supreme Court: https://courtofappeal.lk/?page_id=302
10. LawNet / Ministry of Justice portal lists legislative enactments, consolidated legislation, core legislation, NLR, SLR, Supreme Court Judgements, Court of Appeal Judgements, and local legal links: https://www.lawnet.gov.lk/
