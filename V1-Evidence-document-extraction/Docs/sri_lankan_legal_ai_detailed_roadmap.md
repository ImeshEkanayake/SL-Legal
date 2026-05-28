# Detailed Roadmap for a Sri Lankan Legal AI System

**Purpose:** Build a production-grade lawyer-assistance system for Sri Lankan legal research, case-specific retrieval, argument construction, adversarial simulation, and litigation strategy support.

**Product-build posture:** This is a full product build, not an MVP. The roadmap may use staged delivery and internal gates, but the target is a production-grade legal workflow product with reliable corpus coverage, evaluation, security, auditability, and lawyer review built in from the beginning.

**Implementation roadmap:** The production build execution plan, including the
Codex-like UI direction, MECE case structuring agent, test strategy, load
testing, code review gates, and release readiness gates, is maintained in
`Docs/sl_legal_assist_production_build_roadmap.md`.

**Core split:**

1. **Part 1: Case-Specific Legal Retrieval**  
   Find relevant documents, statutes, procedural rules, constitutional provisions, gazettes, and cases for a specific case.

2. **Part 2: Argument and Strategy Engine**  
   Build arguments, counterarguments, stress-test legal positions, rank risks, and generate a litigation strategy report.

This system should assist lawyers. It should not present itself as replacing lawyers, judges, or legal judgment.

---

## 0. Product Principles

The system should be built around the following principles:

```text
1. Citation-first
   Every legal answer must be grounded in source documents.

2. Authority-aware
   Supreme Court precedent, Court of Appeal precedent, statutes, rules, gazettes, and secondary material must be ranked differently.

3. Human-in-the-loop
   Lawyers must review, approve, reject, or edit all outputs.

4. Retrieval before reasoning
   The system should not generate arguments until it has retrieved the relevant legal materials.

5. No uncited legal conclusions
   If the system cannot find authority, it should say so.

6. Version-controlled law
   Statutes, rules, regulations, and gazettes must be tied to date, amendment history, and effective period.

7. Multilingual readiness
   Sri Lankan legal materials may appear in English, Sinhala, and Tamil.
   For acquisition, prefer official English where it exists; do not spend storage or indexing effort on Sinhala/Tamil duplicates unless English is absent, incomplete, disputed, or legally important for the specific source.

8. Auditability
   Every generated argument should be traceable back to documents, passages, and retrieval steps.

9. Research-pack-bounded strategy
   Argument generation, counterargument simulation, and strategy reporting must use only the retrieved, cited Legal Research Pack for the case. If a necessary authority is not in the research pack, the system must retrieve it, flag it as missing, or ask for lawyer review instead of inventing or relying on unstated legal material.
```

---

# Executive Roadmap

## Suggested timeline

A serious production-grade system should be treated as a **12-18 month build**, depending on team size, data availability, licensing, and the quality target.

| Phase | Timeline | Main Goal | Output |
|---|---:|---|---|
| Phase 0 | Month 0-1 | Product/legal definition | Scope, authority model, risk policy |
| Phase 1 | Month 1-3 | Legal corpus acquisition | Source registry, licence map, corpus plan |
| Phase 2 | Month 2-5 | Ingestion and document processing | Parsed and searchable documents |
| Phase 3 | Month 3-6 | Legal data schema and ontology | Structured legal database model |
| Phase 4 | Month 5-8 | Part 1 retrieval engine | Case-specific legal research pack |
| Phase 5 | Month 7-10 | Part 1 evaluation and hardening | Retrieval accuracy benchmark |
| Phase 6 | Month 9-12 | Part 2 argument builder | Argument/counterargument drafts |
| Phase 7 | Month 11-14 | Adversarial simulation | Stress-tested legal strategy report |
| Phase 8 | Month 12-15 | Lawyer workflow UI | Production user workspace |
| Phase 9 | Month 1-16 | Technical architecture | Production architecture, APIs, storage, orchestration |
| Phase 10 | Month 13-16 | Security, compliance, audit | Safe enterprise-grade deployment |
| Phase 11 | Month 15-18 | Production pilot | Controlled launch with lawyers |
| Phase 12 | Month 16-18+ | Continuous improvement | Legal updates, feedback loops, model improvement |

These phases overlap. Data ingestion, evaluation, security, and legal review should run continuously.

---

# Phase 0: Product, Legal, and Authority Definition

## Goal

Define exactly what the system is allowed to do, what it must not do, and how legal authority is ranked.

## Key decisions

### 0.1 Define the product boundary

The system should be positioned as:

```text
Lawyer-assistance platform for:
- Legal research
- Case-law retrieval
- Statutory retrieval
- Procedural rule retrieval
- Argument drafting assistance
- Counterargument discovery
- Litigation risk analysis
- Case preparation support
```

It should not be positioned as:

```text
- A judge predictor
- A replacement for legal advice
- A replacement for lawyers
- A guaranteed outcome predictor
- A filing system that submits documents without review
```

## 0.2 Define authority hierarchy

The system needs a formal authority-ranking model.

```text
Authority Level 1: Constitution
Authority Level 2: Statutes / Acts of Parliament
Authority Level 3: Supreme Court judgments
Authority Level 4: Court of Appeal judgments
Authority Level 5: Regulations / rules / gazettes, depending on legal context
Authority Level 6: High Court / specialist court decisions
Authority Level 7: Tribunal decisions
Authority Level 8: Secondary materials, commentary, textbooks, practice guides
Authority Level 9: Lawyer-uploaded examples and sample pleadings
```

The system must know that not all sources are equal.

## 0.3 Define safety rules

```text
- No legal conclusion without citation.
- No hidden source usage.
- No fabricated cases, statutes, sections, or quotes.
- No claim that the result is legal advice unless a lawyer approves it.
- No prediction of court outcome as certainty.
- No use of confidential client material for model training without permission.
- Every generated argument must include supporting sources and known weaknesses.
```

## 0.4 Deliverables

```text
- Product scope document
- Legal authority ranking policy
- Source reliability policy
- Human-review policy
- Data confidentiality policy
- Output-risk policy
- First version of legal taxonomy
```

---

# Phase 1: Legal Corpus Acquisition

## Goal

Collect, classify, and legally validate the documents the system will use.

## 1.1 Corpus categories

The corpus should be divided into primary law, procedure, case law, practice material, secondary material, and user case files.

```text
Sri Lankan Legal Corpus
│
├── 1_primary_law
│   ├── constitution
│   ├── acts
│   ├── amendments
│   ├── bills
│   ├── regulations
│   ├── gazettes
│   └── extraordinary_gazettes
│
├── 2_procedural_law
│   ├── supreme_court_rules
│   ├── court_of_appeal_rules
│   ├── civil_procedure_code
│   ├── code_of_criminal_procedure
│   ├── evidence_ordinance
│   ├── judicature_act
│   ├── limitation_law
│   └── specialist_court_rules
│
├── 3_case_law
│   ├── supreme_court
│   ├── court_of_appeal
│   ├── commercial_high_court
│   ├── high_court
│   ├── district_court
│   ├── magistrates_court
│   ├── labour_tribunal
│   └── specialist_tribunals
│
├── 4_litigation_documents
│   ├── plaints
│   ├── answers
│   ├── petitions
│   ├── affidavits
│   ├── written_submissions
│   ├── motions
│   ├── objections
│   ├── charge_sheets
│   ├── indictments
│   ├── bail_applications
│   └── appeal_documents
│
├── 5_administrative_material
│   ├── judicial_service_commission_circulars
│   ├── court_registry_notices
│   ├── ministry_circulars
│   ├── attorney_general_material
│   ├── police_forms_and_reports
│   └── government_guidelines
│
├── 6_secondary_material
│   ├── law_report_headnotes
│   ├── legal_commentary
│   ├── academic_articles
│   ├── basl_material
│   ├── practice_guides
│   └── textbooks_if_licensed
│
└── 7_user_case_files
    ├── client_facts
    ├── evidence_documents
    ├── witness_statements
    ├── contracts
    ├── correspondence
    ├── police_records
    ├── prior_orders
    └── opponent_documents
```

## 1.2 Source registry

Every source should be registered before ingestion.

```json
{
  "source_id": "SC_OFFICIAL_2026",
  "source_name": "Supreme Court official judgments",
  "source_type": "case_law",
  "jurisdiction": "Sri Lanka",
  "authority_level": "Supreme Court",
  "source_reliability_tier": "official / verified / licensed / lawyer-uploaded / unverified",
  "access_type": "public / licensed / private",
  "licence_status": "approved / pending / restricted",
  "acquisition_difficulty": "easy / moderate / difficult / partnership_required",
  "language": ["English"],
  "download_method": "manual / crawler / API / upload",
  "refresh_frequency": "daily / weekly / monthly",
  "trust_level": "primary",
  "notes": "Official court source"
}
```

## 1.3 Source reliability and acquisition tiers

The system should distinguish legal authority from source reliability. A document may be legally important but difficult to acquire reliably, especially where court material is fragmented, scanned, unpublished, privately held, or only available through licensed providers.

```text
Tier A: Reliable official/public sources
- Constitution
- Acts and amendments from official publication channels
- Gazettes and extraordinary gazettes from official publication channels
- Court rules and procedural materials from official publication channels
- Officially published Supreme Court and Court of Appeal judgments, where available

Expected treatment:
- Highest source reliability
- Suitable for automated refresh where permitted
- Preferred for citation-backed outputs
- Must still be versioned and checked for amendments or later treatment

Tier B: Verified but harder-to-acquire court materials
- Older judgments available only through scanned reports or archives
- Commercial law-report databases
- Court of Appeal / High Court / specialist court materials with incomplete public access
- Registry, tribunal, or lower-court records obtained through partnerships or uploads

Expected treatment:
- High legal value, but acquisition and licensing risk must be tracked
- Require provenance, licence review, OCR quality checks, and manual validation
- Should be marked with source limitations in the Legal Research Pack

Tier C: Lawyer-uploaded or firm-provided materials
- Pleadings
- Written submissions
- Prior case files
- Internal research notes
- Sample documents

Expected treatment:
- Useful for workflow and drafting patterns
- Not treated as legal authority unless independently supported
- Must be isolated by tenant and matter
- Must not be used for model training without explicit permission

Tier D: Secondary or unverified materials
- Commentary
- Academic material
- Training manuals
- Web pages
- Unverified case summaries

Expected treatment:
- Used only as background or discovery aids
- Never sufficient for legal conclusions by itself
- Must be clearly labelled as secondary or unverified
```

## 1.4 Corpus priority order

Start with the materials that give the highest legal value.

```text
Priority 1:
- Constitution
- Core Acts
- Procedural law
- Evidence Ordinance
- Supreme Court judgments
- Court of Appeal judgments

Priority 2:
- Gazettes and extraordinary gazettes
- Court rules
- Commercial High Court judgments
- Specialist tribunal material

Priority 3:
- Lower court material
- Pleadings and written submissions
- Lawyer-uploaded anonymised case files
- Secondary commentary

Priority 4:
- Academic literature
- Practice guides
- Training manuals
- Historical materials
```

### Current Acts and Bills ingestion note

The Parliament Acts and Government Bills corpus has an initial indexed acquisition pass and should now be treated as a maintained source track, not a blocker for the next corpus categories.

Current local tracking files:

```text
data/manifests/document_manifest.csv
data/manifests/legal_instrument_registry.csv
data/manifests/government_bill_registry.csv
data/manifests/missing_act_pdf_report.csv
data/manifests/parliament_search_ui_audit.csv
data/manifests/parliament_search_ui_year_counts.csv
data/indexes/corpus_index.json
```

Operational note:

```text
- Refresh Acts and Government Bills periodically from both CSV exports and search-result pages.
- Treat the search UI audit as a supplement because some rows appear in search results but not in CSV exports.
- Keep missing PDFs as explicit manifest rows instead of blocking the rest of the corpus build.
- Return to Acts/Bills later for alternate-source PDF recovery, OCR, Sinhala/Tamil completion, bill-to-act linking, amendment chains, and current-force status.
```

### Current Hansard ingestion note

The Parliament daily Hansard and corrected-volume English listings are now active source tracks. The downloader writes to the shared manifest, a dedicated Hansard registry, and the corpus index.

Current local tracking files:

```text
scripts/acquire_parliament_hansards.py
data/manifests/hansard_registry.csv
data/manifests/document_manifest.csv
data/manifests/missing_data_register.csv
data/indexes/corpus_index.json
```

Operational note:

```text
- Prefer English Hansard PDFs; do not acquire Sinhala/Tamil duplicates where English exists.
- Treat online Hansard coverage as partial, not complete 1948-present coverage.
- Keep pre-online Hansards, committee proceedings, corrected-volume indexes, and archival parliamentary material as explicit missing/acquisition items.
- Link Hansard records later to Bills, Acts, constitutional amendments, and special determinations.
```

## 1.5 Deliverables

```text
- Source registry
- Source reliability and acquisition-tier model
- Licence and copyright risk map
- Public-source download plan
- Private-source partnership plan
- Corpus priority list
- Refresh schedule
- Data-retention policy
```

---

# Phase 2: Ingestion and Document Processing

## Goal

Convert PDFs, gazettes, judgments, and user-uploaded documents into clean, structured, searchable legal data.

## 2.1 Ingestion pipeline

```text
Document source
    ↓
Download / upload / import
    ↓
File validation
    ↓
Hashing and duplicate detection
    ↓
OCR if required
    ↓
Text extraction
    ↓
Layout extraction
    ↓
Language detection
    ↓
Document classification
    ↓
Legal segmentation
    ↓
Metadata extraction
    ↓
Citation extraction
    ↓
Storage
    ↓
Indexing
```

## 2.2 File validation

Before processing, the system should check:

```text
- File type
- File size
- OCR requirement
- Language
- Source identity
- Duplicate status
- Corruption status
- Whether the file is confidential
- Whether the file is allowed under licence
```

## 2.3 Document classification

The system should classify each uploaded document.

```text
Possible document classes:
- Constitution
- Act
- Amendment Act
- Bill
- Gazette
- Court rule
- Supreme Court judgment
- Court of Appeal judgment
- Commercial High Court judgment
- Tribunal decision
- Plaint
- Answer
- Petition
- Affidavit
- Written submission
- Motion
- Objection
- Contract
- Police report
- Medical report
- Land document
- Correspondence
- Unknown / needs human review
```

## 2.4 Legal segmentation

Different documents require different segmentation.

### Statutes and Acts

```text
Act
├── Long title
├── Preamble
├── Parts
├── Chapters
├── Sections
├── Subsections
├── Definitions
├── Offences
├── Penalties
├── Powers
├── Procedures
├── Transitional provisions
├── Repeals
├── Schedules
└── Amendment history
```

### Constitution

```text
Constitution
├── Chapter
├── Article
├── Clause
├── Fundamental right
├── Institutional power
├── Jurisdiction provision
├── Amendment history
└── Cross-reference links
```

### Court judgments

```text
Judgment
├── Case name
├── Court
├── Case number
├── Date
├── Bench / judge
├── Parties
├── Counsel
├── Procedural history
├── Facts
├── Issues
├── Appellant / petitioner arguments
├── Respondent arguments
├── Statutory provisions considered
├── Cases cited
├── Court reasoning
├── Ratio decidendi
├── Obiter dicta
├── Holding
├── Final order
├── Costs / relief
└── Later treatment, if known
```

### Gazettes

```text
Gazette
├── Gazette number
├── Date
├── Language
├── Part / section
├── Ministry / department
├── Instrument type
├── Subject matter
├── Legal authority cited
├── Regulation / order / notice text
├── Effective date
└── Related statute
```

### Pleadings and litigation documents

```text
Litigation document
├── Court
├── Case number
├── Parties
├── Document type
├── Filing party
├── Date
├── Relief sought
├── Material facts
├── Legal grounds
├── Evidence referred to
├── Statutory provisions cited
├── Cases cited
├── Procedural requests
├── Prayer / final request
└── Verification / affidavit link
```

## 2.5 OCR and layout requirements

Legal PDFs are often scanned, especially older materials. The OCR system should handle:

```text
- English OCR
- Sinhala OCR
- Tamil OCR
- Mixed-language documents
- Footnotes
- tables
- stamps and seals
- page numbers
- paragraph numbers
- columns in gazettes
- handwritten notes, if possible
```

A confidence score should be attached to OCR output.

```json
{
  "text": "extracted text",
  "ocr_confidence": 0.91,
  "language": "English",
  "page_number": 12,
  "layout_type": "paragraph",
  "needs_human_review": false
}
```

## 2.6 Deliverables

```text
- Ingestion service
- OCR pipeline
- Document classifier
- Legal segmentation pipeline
- Metadata extraction pipeline
- Citation extraction pipeline
- Document quality dashboard
- Human-review queue for uncertain documents
```

---

# Phase 3: Legal Data Schema and Knowledge Graph

## Goal

Represent legal documents in a way that supports fast retrieval, legal reasoning, authority ranking, and citation tracing.

## 3.1 Core database entities

```text
Core entities:
- SourceDocument
- LegalProvision
- CaseJudgment
- CaseCitation
- LegalIssue
- LegalPrinciple
- ProceduralRule
- GazetteInstrument
- LitigationDocument
- Party
- Court
- Judge
- Counsel
- Argument
- EvidenceItem
- Relief
- CaseProfile
- RetrievalResult
```

## 3.2 SourceDocument schema

```json
{
  "document_id": "doc_001",
  "title": "Example Judgment",
  "document_type": "Supreme Court judgment",
  "source": "official court source",
  "court": "Supreme Court",
  "jurisdiction": "Sri Lanka",
  "date": "2025-01-20",
  "language": "English",
  "authority_level": "binding",
  "source_url": "...",
  "licence_status": "approved",
  "file_hash": "...",
  "version": "1.0",
  "created_at": "...",
  "updated_at": "..."
}
```

## 3.3 LegalProvision schema

```json
{
  "provision_id": "act_001_s_12",
  "act_name": "Example Act",
  "act_number": "12 of 2000",
  "section": "12",
  "subsection": "1",
  "text": "...",
  "effective_from": "2000-06-01",
  "effective_to": null,
  "amended_by": ["Amendment Act 5 of 2010"],
  "repealed": false,
  "subject_tags": ["criminal procedure", "evidence"],
  "related_cases": ["case_001", "case_002"]
}
```

## 3.4 CaseJudgment schema

```json
{
  "case_id": "sc_appeal_001_2025",
  "case_name": "A v B",
  "court": "Supreme Court",
  "case_number": "SC Appeal 001/2025",
  "date": "2025-03-10",
  "bench": ["Justice X", "Justice Y"],
  "case_type": "civil appeal",
  "procedural_posture": "appeal",
  "facts_summary": "...",
  "issues": ["Whether ..."],
  "holding": "...",
  "ratio": "...",
  "obiter": "...",
  "final_order": "...",
  "statutes_considered": ["Evidence Ordinance s. ..."],
  "cases_cited": ["case_123"],
  "later_treatment": "unknown / followed / distinguished / overruled",
  "authority_score": 0.95
}
```

## 3.5 Citation graph

The system should create a legal knowledge graph.

```text
Case A cites Case B
Case A follows Case B
Case A distinguishes Case C
Case A overrules Case D
Case A applies Statute X section 10
Statute X section 10 is amended by Act Y
Gazette Z is issued under Statute X
Court Rule R governs Procedure P
```

## 3.6 Later-treatment labels

The system should detect and store case treatment.

```text
- followed
- applied
- considered
- referred to
- distinguished
- doubted
- not followed
- overruled
- reversed
- affirmed
- modified
- pending appeal
- unknown
```

## 3.7 Deliverables

```text
- Legal data schema v1
- Legal issue taxonomy
- Authority ranking model
- Citation parser
- Citation graph
- Statute amendment tracker
- Case treatment extractor
- Annotation guidelines for lawyers
```

---

# Phase 4: Part 1 — Case-Specific Legal Retrieval Engine

## Goal

Given a specific case, find the most relevant legal materials and explain why they matter.

## 4.1 User input

The lawyer should be able to upload or enter:

```text
- Case facts
- Client interview notes
- Complaint / plaint / petition
- Answer / objections
- Charge sheet / indictment
- B report / police record
- Contract
- Land document
- Emails / letters / WhatsApp messages
- Medical reports
- Previous court orders
- Opponent submissions
- Lawyer's specific legal questions
```

## 4.2 Case Profile extraction

The system should convert raw case files into a structured profile.

```json
{
  "case_profile_id": "profile_001",
  "case_type": "civil / criminal / writ / FR / commercial / labour / land / family",
  "court_level": "District Court / High Court / Court of Appeal / Supreme Court",
  "procedural_stage": "pre-filing / trial / appeal / revision / writ / FR application",
  "parties": [],
  "material_facts": [],
  "disputed_facts": [],
  "legal_issues": [],
  "possible_claims": [],
  "possible_defences": [],
  "relief_sought": [],
  "evidence_available": [],
  "missing_evidence": [],
  "deadlines": [],
  "limitation_risks": [],
  "jurisdiction_risks": []
}
```

## 4.3 Legal issue generation

The system should identify possible legal issues.

```text
Examples:
- Jurisdiction
- Maintainability
- Limitation
- Locus standi
- Cause of action
- Burden of proof
- Standard of proof
- Admissibility of evidence
- Natural justice
- Legitimate expectation
- Abuse of process
- Breach of contract
- Fundamental rights violation
- Writ jurisdiction
- Bail
- Mens rea
- Chain of custody
- Land title
- Prescription
- Damages
- Injunction
```

## 4.4 Query planner

Instead of one search query, the system should generate multiple targeted searches.

```text
For one case, create separate searches for:
- Direct statutory provisions
- Procedural rules
- Evidence rules
- Binding Supreme Court precedent
- Court of Appeal precedent
- Factually similar cases
- Cases with similar legal issue
- Cases with similar relief
- Cases with similar procedural posture
- Opponent-side authorities
- Risk authorities
```

## 4.5 Retrieval architecture

```text
Case Profile
    ↓
Query Planner
    ↓
Metadata Filter
    ↓
Keyword Search
    ↓
Semantic Vector Search
    ↓
Citation Graph Expansion
    ↓
Cross-Encoder Reranker
    ↓
Authority-Aware Ranking
    ↓
Legal Research Pack
```

## 4.6 Search layers

### Metadata filtering

```text
- Court
- Jurisdiction
- Date range
- Subject area
- Document type
- Case type
- Procedural stage
- Statute involved
- Language
- Authority level
```

### Keyword retrieval

Useful for:

```text
- Case numbers
- Statute sections
- Exact legal phrases
- Party names
- Offence names
- Relief types
- Procedural terms
```

### Semantic retrieval

Useful for:

```text
- Similar facts
- Similar legal questions
- Similar defences
- Similar remedies
- Similar evidentiary problems
- Similar procedural objections
```

### Citation graph expansion

Useful for:

```text
- Cases cited by relevant cases
- Later cases citing the relevant cases
- Cases that followed a leading case
- Cases that distinguished a leading case
- Overruled or weakened authorities
```

### Reranking

A reranker should consider:

```text
- Binding authority
- Court hierarchy
- Factual similarity
- Legal issue similarity
- Procedural-stage similarity
- Recency
- Leading-case status
- Later treatment
- Citation frequency
- Clarity of ratio
- Whether the case supports or weakens the user's side
```

## 4.7 Output: Legal Research Pack

The output of Part 1 should be a structured research pack.

```text
Legal Research Pack
├── Research pack ID and version
├── Case profile summary
├── Key legal issues
├── Citation inventory
├── Relevant constitutional provisions
├── Relevant statutes and sections
├── Relevant procedural rules
├── Relevant evidence rules
├── Binding Supreme Court authorities
├── Relevant Court of Appeal authorities
├── Factually similar cases
├── Cases supporting our side
├── Cases supporting the opponent's side
├── Dangerous or adverse cases
├── Overruled / distinguished / risky authorities
├── Source reliability notes
├── Missing sources to check manually
└── Research confidence summary
```

## 4.8 Retrieval result format

Each result should be explainable.

```json
{
  "result_id": "retrieval_001",
  "document_title": "Example Case",
  "document_type": "Supreme Court judgment",
  "source_id": "SC_OFFICIAL_2026",
  "source_reliability_tier": "official",
  "court": "Supreme Court",
  "date": "2025-02-01",
  "authority_level": "binding",
  "citation": "official citation or neutral citation where available",
  "relevance_score": 0.91,
  "legal_issue_match": ["burden of proof", "contract interpretation"],
  "fact_similarity": 0.78,
  "supports": "our side / opponent / neutral / risk",
  "important_passages": [
    {
      "page": 12,
      "paragraph": 34,
      "text": "..."
    }
  ],
  "why_relevant": "This case discusses the same legal issue and similar facts.",
  "known_risk": "Later case may have distinguished this principle."
}
```

## 4.9 Part 1 acceptance criteria

Part 1 should not be considered production-ready until:

```text
- Every result has a source citation.
- The system can explain why each result is relevant.
- The system separates binding, persuasive, and secondary authority.
- The system identifies adverse authorities, not only favourable ones.
- The system can say when no reliable authority was found.
- Lawyers can approve/reject search results.
- Retrieval quality is measured using real lawyer-reviewed test cases.
- The Legal Research Pack is versioned so Part 2 can prove exactly which cited sources were available when argument and strategy outputs were generated.
```

---

# Phase 5: Part 1 Evaluation and Hardening

## Goal

Prove that the retrieval system is accurate enough to support lawyers.

## 5.1 Build a legal benchmark set

Create a benchmark with lawyer-annotated examples.

```text
Benchmark size progression:
- 25 cases for initial testing
- 100 cases for internal validation
- 300-500 cases for production confidence
- 1,000+ cases for mature evaluation
```

Each benchmark case should include:

```text
- Case facts
- Case type
- Legal issues
- Correct statutes
- Correct procedural rules
- Important cases
- Adverse cases
- Irrelevant but tempting cases
- Lawyer explanation
```

## 5.2 Metrics

### Retrieval metrics

```text
- Recall@10
- Recall@20
- Precision@10
- Mean Reciprocal Rank
- NDCG
- Adverse authority detection rate
- Binding authority detection rate
- Statute-section accuracy
- Citation accuracy
```

### Legal quality metrics

```text
- Did the system find the leading authority?
- Did it find adverse authority?
- Did it confuse similar legal issues?
- Did it rank lower authority above higher authority incorrectly?
- Did it cite outdated or amended law?
- Did it explain relevance correctly?
```

### Safety metrics

```text
- Hallucinated citation rate
- Unsupported legal conclusion rate
- Confidential data leakage rate
- Wrong-law-version rate
- Overconfidence rate
```

## 5.3 Human evaluation workflow

```text
System retrieves results
    ↓
Lawyer reviews result relevance
    ↓
Lawyer labels result:
    - highly relevant
    - somewhat relevant
    - irrelevant
    - adverse authority
    - procedural risk
    - outdated law
    - wrong jurisdiction
    ↓
Labels improve reranking and evaluation
```

## 5.4 Deliverables

```text
- Retrieval benchmark dataset
- Evaluation dashboard
- Lawyer annotation interface
- Error analysis report
- Retrieval improvement backlog
- Production readiness scorecard
```

---

# Phase 6: Part 2 — Argument Builder

## Goal

Use the cited Legal Research Pack to generate structured legal arguments for the lawyer.

Part 2 must not introduce legal authorities, statutory provisions, case names, quotes, or legal propositions that are absent from the current Legal Research Pack. If the argument engine needs additional authority, it must request retrieval expansion first, then regenerate from the updated research pack.

## 6.1 Research-pack boundary

Every argument-generation run should be tied to a specific research pack.

```json
{
  "argument_run_id": "arg_run_001",
  "case_profile_id": "profile_001",
  "research_pack_id": "research_pack_001",
  "research_pack_version": "v3",
  "allowed_source_ids": ["doc_001", "case_123", "act_001_s_12"],
  "allowed_passage_ids": ["passage_001", "passage_002"],
  "missing_authority_requests": [],
  "generated_at": "2026-05-21T10:30:00Z"
}
```

Hard rules:

```text
- The LLM may reason over cited passages in the research pack.
- The LLM may not cite or quote authorities outside the research pack.
- The LLM may not use general legal memory as authority.
- Any unsupported proposition must be marked as needing retrieval or lawyer review.
- Every legal proposition in an argument must map to at least one source ID or passage ID.
- Strategy reports must include the research pack version used to generate them.
```

## 6.2 Argument object

Every generated argument should have a clear structure.

```json
{
  "argument_id": "arg_001",
  "research_pack_id": "research_pack_001",
  "research_pack_version": "v3",
  "side": "plaintiff / accused / respondent / petitioner / appellant",
  "legal_issue": "burden of proof",
  "argument_title": "The opposing party has failed to prove the required element",
  "position": "...",
  "legal_rule": "...",
  "supporting_statutes": [],
  "supporting_cases": [],
  "supporting_facts": [],
  "supporting_evidence": [],
  "supporting_passage_ids": [],
  "required_elements": [],
  "satisfied_elements": [],
  "unsatisfied_elements": [],
  "unsupported_or_missing_authorities": [],
  "counterarguments_expected": [],
  "rebuttal_options": [],
  "risk_level": "low / medium / high",
  "impact_level": "high / medium / low",
  "confidence": 0.82,
  "lawyer_review_status": "pending"
}
```

## 6.3 Element-based reasoning

For each claim or defence, the system should identify required elements.

```text
Claim / defence
    ↓
Required legal elements
    ↓
Facts supporting each element
    ↓
Evidence supporting each fact
    ↓
Law supporting the legal rule
    ↓
Cases interpreting the rule
    ↓
Weak or missing elements
```

## 6.4 Argument types

The system should classify arguments by type.

```text
- Constitutional argument
- Statutory interpretation argument
- Procedural objection
- Jurisdiction objection
- Limitation argument
- Factual insufficiency argument
- Evidentiary admissibility argument
- Burden of proof argument
- Standard of proof argument
- Natural justice argument
- Abuse of process argument
- Remedy / relief argument
- Public policy argument
- Equity / fairness argument
- Precedent-based argument
- Distinguishing argument
```

## 6.5 Argument drafting modes

The system should support different drafting styles.

```text
1. Research mode
   Gives concise legal reasoning with citations.

2. Submission mode
   Converts argument into written-submission style.

3. Court-preparation mode
   Gives oral argument notes.

4. Risk-review mode
   Highlights weaknesses and missing support.

5. Client-explanation mode
   Explains the case in plain language.
```

## 6.6 Deliverables

```text
- Argument generator
- Element mapping engine
- Fact-to-evidence mapper
- Research-pack boundary validator
- Citation-backed argument format
- Lawyer-editable argument workspace
- Argument export format
```

---

# Phase 7: Adversarial Simulation and Stress Testing

## Goal

Find how the opposing side can attack the case, then generate rebuttals and risk rankings.

## 7.1 Opponent simulation

The system should simulate the other side across multiple attack categories.

```text
Opponent attack categories:
- No jurisdiction
- Wrong forum
- Limitation / prescribed claim
- No cause of action
- Lack of standing
- Defective pleading
- Procedural non-compliance
- Burden of proof not met
- Evidence inadmissible
- Document authenticity challenged
- Witness credibility challenged
- Facts are disputed
- Alternative facts explain the case
- Statute interpreted differently
- Precedent distinguishable
- Contrary precedent applies
- Relief is unavailable
- Discretion should not be exercised
- Abuse of process
- Delay / laches
- Suppression or non-disclosure of material facts
```

## 7.2 Counterprecedent retrieval

For every argument, the system should search for adverse authority through the retrieval engine before strategy generation. Counterprecedent discovery is a retrieval expansion step, not a permission for the strategy engine to rely on uncited model knowledge.

```text
- Cases that contradict the argument
- Cases where similar arguments failed
- Cases where courts distinguished similar facts
- Cases where relief was refused
- Cases where procedural defects defeated the case
- Cases where evidence was excluded
```

If new adverse material is found, the system should update the Legal Research Pack and generate the strategy report from the new pack version.

```text
Argument draft
    ↓
Counterprecedent retrieval request
    ↓
Retrieved adverse authorities
    ↓
Research pack updated and versioned
    ↓
Strategy generation using only the updated cited pack
```

## 7.3 Stress-test matrix

Each argument should be tested against a matrix.

```text
Argument Stress Test
├── Is there binding support?
├── Is there contrary binding authority?
├── Is the statute current?
├── Are the facts strong enough?
├── Is the evidence admissible?
├── Is the procedure correct?
├── Is the court the correct forum?
├── Is limitation a problem?
├── Can the opponent distinguish our cases?
├── Can we distinguish opponent cases?
├── Is the relief legally available?
└── What must the lawyer verify manually?
```

## 7.4 Argument scoring

A suggested scoring model:

```text
Argument Strength Score =
    Authority score
  + Statutory clarity score
  + Factual support score
  + Evidence support score
  + Procedural safety score
  + Relief availability score
  - Contrary authority penalty
  - Missing evidence penalty
  - Procedural defect penalty
  - Uncertainty penalty
```

## 7.5 Impact categories

```text
High Impact
- Supported by binding authority
- Strong statutory basis
- Strong factual match
- Strong evidence
- Low procedural risk
- Opponent has weak rebuttal

Medium Impact
- Supported by persuasive authority
- Some factual or legal ambiguity
- Evidence is incomplete but usable
- Opponent has plausible rebuttal

Low Impact
- Weak or indirect authority
- Factually distinguishable precedent
- Procedurally risky
- Missing evidence
- More useful as backup or settlement pressure
```

## 7.6 Output: Strategy Report

```text
Case Strategy Report
├── Research pack ID and version used
├── Executive summary
├── Key legal issues
├── Strongest arguments
├── Medium-strength arguments
├── Backup arguments
├── Arguments not recommended
├── Opponent's likely arguments
├── Our rebuttals
├── Dangerous precedents
├── Procedural risks
├── Evidence risks
├── Missing documents
├── Questions to ask client
├── Questions for cross-examination
├── Suggested written-submission outline
├── Settlement leverage points
├── Unsupported points requiring lawyer review
└── Final lawyer-review checklist
```

## 7.7 Deliverables

```text
- Opponent simulation engine
- Counterprecedent retrieval module
- Argument stress-test module
- Research-pack compliance checker
- Impact ranking model
- Strategy report generator
- Lawyer feedback loop
```

---

# Phase 8: Lawyer Workflow UI

## Goal

Create a usable workspace for lawyers, not just a chatbot.

## 8.1 Main UI modules

```text
Lawyer Workspace
├── Case dashboard
├── Document upload area
├── Case profile editor
├── Legal research results
├── Statute viewer
├── Judgment viewer
├── Citation graph viewer
├── Argument builder
├── Opponent simulation panel
├── Risk dashboard
├── Drafting workspace
├── Review and approval workflow
└── Export center
```

## 8.2 Case dashboard

The dashboard should show:

```text
- Case name
- Court
- Case type
- Procedural stage
- Key deadlines
- Uploaded documents
- Key legal issues
- Retrieval status
- Argument status
- Risk status
- Lawyer review status
```

## 8.3 Research result UI

Each research result should show:

```text
- Title
- Source
- Authority level
- Relevance score
- Support/opposition/risk label
- Important quoted passage
- Why it matters
- Later treatment
- Lawyer actions:
  - Save
  - Reject
  - Mark as adverse
  - Add to argument
  - Request deeper search
```

## 8.4 Argument UI

Each argument should be editable.

```text
Argument Card
├── Argument title
├── Research pack version
├── Legal issue
├── Our position
├── Legal rule
├── Supporting authorities
├── Supporting passage IDs / citations
├── Supporting facts
├── Supporting evidence
├── Opponent attacks
├── Rebuttals
├── Missing or unsupported authorities
├── Impact level
├── Risk level
└── Lawyer notes
```

## 8.5 Exports

The system should export:

```text
- Legal research memo
- Strategy report
- Case-law table
- Statutory provision table
- Citation and source appendix
- Argument outline
- Written-submission draft
- Client explanation note
- Cross-examination preparation note
- Evidence gap checklist
```

## 8.6 Deliverables

```text
- Web application
- Case workspace
- Document viewer
- Research result viewer
- Argument builder UI
- Review workflow
- Export templates
```

---

# Phase 9: Technical Architecture

## Goal

Build a scalable, secure, and cost-efficient architecture.

This is a cross-cutting production workstream that starts early and continues through retrieval, argument generation, UI, pilot, and rollout.

## 9.1 High-level architecture

```text
Frontend Web App
    ↓
API Gateway
    ↓
Authentication and RBAC
    ↓
Case Management Service
    ↓
Document Service
    ↓
Ingestion Pipeline
    ↓
OCR and Layout Parser
    ↓
Legal Document Classifier
    ↓
Metadata and Citation Extractor
    ↓
Storage Layer
    ├── Object Storage
    ├── PostgreSQL
    ├── Search Index
    ├── Vector Database
    └── Knowledge Graph
    ↓
Retrieval Engine
    ↓
Reranker
    ↓
Research Pack Boundary Service
    ↓
LLM Orchestration Layer
    ↓
Citation and Source-Compliance Validator
    ↓
Evaluation and Audit Layer
```

## 9.2 Suggested storage components

```text
Object storage:
- Original PDFs
- OCR files
- extracted text
- page images

PostgreSQL:
- users
- cases
- metadata
- document records
- legal provisions
- case profiles
- legal research packs
- research pack versions
- argument objects
- argument generation runs
- review status
- source reliability registry

Search engine:
- BM25 keyword search
- filters
- exact legal phrase search

Vector database:
- semantic document chunks
- issue embeddings
- fact-pattern embeddings
- argument embeddings

Graph database or graph table:
- case-to-case citations
- statute-to-case links
- case treatment
- amendment relationships
```

## 9.3 Model stack

```text
Model components:
- OCR model
- Layout detection model
- Document classifier
- Legal NER model
- Citation parser
- Embedding model
- Cross-encoder reranker
- LLM for extraction
- LLM for legal issue generation
- LLM for argument drafting
- LLM for adversarial simulation
- Citation grounding validator
- Research-pack boundary validator
- Safety / validation model
```

## 9.4 LLM usage strategy

The system should avoid sending entire documents to the LLM.

```text
Use LLMs for:
- Case profile extraction
- Legal issue generation
- Passage summarisation
- Argument drafting
- Counterargument drafting
- Explanation generation

Do not use LLMs for:
- Bulk scanning every document
- Replacing database search
- Unverified citation generation
- Final legal conclusions without source grounding
- Strategy generation from general legal memory
- Introducing authorities outside the current Legal Research Pack
```

## 9.5 Cost optimisation

```text
- Precompute embeddings
- Chunk documents once
- Cache retrieval results
- Cache case profiles
- Use keyword + vector search before LLM calls
- Use smaller models for classification
- Use larger models only for final reasoning
- Batch OCR and ingestion
- Avoid re-processing unchanged documents
- Use citation IDs instead of full text where possible
```

## 9.6 Deliverables

```text
- Production architecture design
- Database schema
- API specification
- Search infrastructure
- Vector index
- Knowledge graph
- LLM orchestration service
- Cost monitoring dashboard
```

---

# Phase 10: Security, Privacy, Compliance, and Audit

## Goal

Protect client data, lawyer work product, and confidential case materials.

## 10.1 Security requirements

```text
- Tenant isolation
- Role-based access control
- Case-level permissions
- Encryption at rest
- Encryption in transit
- Secure file upload
- Malware scanning
- Audit logging
- Session management
- Multi-factor authentication
- Data retention controls
- Secure deletion
```

## 10.2 Confidentiality rules

```text
- Do not use client files for training without explicit permission.
- Do not expose one lawyer's case material to another lawyer.
- Do not send confidential material to external APIs unless approved.
- Keep audit logs of who accessed what and when.
- Allow law firms to control retention and deletion.
```

## 10.3 Prompt-injection defence

User-uploaded documents may contain malicious instructions. The system should treat documents as data, not commands.

```text
Rules:
- Uploaded text cannot override system instructions.
- Retrieval passages are quoted as evidence, not instructions.
- LLM prompts should separate instructions from document content.
- Suspicious text should be flagged.
```

## 10.4 Legal-risk controls

```text
- Output disclaimer
- Lawyer approval required
- No automatic filing
- No guarantee of outcome
- Manual verification checklist
- Source confidence indicators
- Warning for missing authorities
- Warning for outdated law
- Block strategy generation when cited-source validation fails
```

## 10.5 Audit trail

The system should store:

```text
- Uploaded files
- Extracted case profile
- Search queries generated
- Documents retrieved
- Passages used
- Legal Research Pack ID and version
- Allowed source IDs and passage IDs for each argument run
- Missing-authority retrieval requests
- Citation-validation failures
- Model outputs
- Lawyer edits
- Lawyer approvals
- Exported reports
```

## 10.6 Deliverables

```text
- Security model
- Privacy policy
- Data-processing policy
- Audit log system
- Prompt-injection defence
- Legal-risk checklist
- Enterprise deployment checklist
```

---

# Phase 11: Production Pilot

## Goal

Test the system with real lawyers on controlled cases before wider launch.

## 11.1 Pilot design

```text
Pilot participants:
- 5-10 lawyers initially
- Different practice areas
- Mix of junior and senior lawyers
- Controlled non-sensitive or anonymised cases first
```

## 11.2 Pilot practice areas

Start with areas where documents and precedent are relatively available.

```text
Good early practice areas:
- Fundamental rights
- Writ applications
- Civil procedure
- Commercial disputes
- Contract disputes
- Evidence issues
- Criminal bail and procedure
```

Avoid starting with areas where facts are highly sensitive or data is hard to obtain.

```text
Harder early areas:
- Family disputes
- Sexual offences
- Child-related matters
- Highly confidential corporate disputes
- Complex land disputes with poor documents
```

## 11.3 Pilot metrics

```text
- Time saved per research task
- Lawyer satisfaction
- Retrieval accuracy
- Number of missed authorities
- Number of wrong authorities
- Citation hallucination rate
- Usefulness of argument drafts
- Quality of counterarguments
- Export quality
- Lawyer trust level
```

## 11.4 Go-live criteria

The system should only move to broader production when:

```text
- Lawyers trust the retrieval results.
- Citation hallucination is close to zero.
- Adverse authorities are surfaced reliably.
- Output is always source-grounded.
- Security review is passed.
- Data licensing is clean.
- Human review workflow is working.
- Known limitations are clearly shown in the UI.
```

## 11.5 Deliverables

```text
- Pilot report
- Error analysis report
- Improved retrieval models
- Improved UI workflow
- Production readiness review
- Launch decision document
```

---

# Phase 12: Continuous Improvement

## Goal

Improve the system after production through feedback, new data, and legal updates.

## 12.1 Feedback loops

```text
Lawyer feedback should improve:
- Document relevance
- Issue classification
- Argument strength scoring
- Counterargument quality
- Citation treatment
- Practice-area templates
```

## 12.2 Continuous data updates

```text
Update schedules:
- New judgments: daily or weekly
- Gazettes: daily or weekly
- Acts and amendments: weekly or monthly
- Court rules: as published
- Secondary commentary: monthly or quarterly
- User-uploaded internal firm documents: on upload
```

## 12.3 Model improvement

```text
Possible improvements:
- Fine-tune legal embeddings
- Fine-tune reranker on lawyer labels
- Improve Sinhala/Tamil retrieval
- Improve citation extraction
- Improve issue taxonomy
- Improve argument scoring model
- Add practice-area-specific workflows
```

## 12.4 Deliverables

```text
- Continuous evaluation dashboard
- Model retraining pipeline
- Legal update pipeline
- Lawyer feedback analytics
- Practice-area expansion plan
```

---

# Workstreams

## Workstream A: Corpus and Licensing

```text
Tasks:
- Identify official legal sources
- Identify commercial/legal database options
- Identify public domain / licence status
- Create source registry
- Create data acquisition contracts if needed
- Create update schedule

Deliverables:
- Source registry
- Licence risk map
- Corpus acquisition plan
- Update policy
```

## Workstream B: Data Engineering

```text
Tasks:
- Build crawlers/importers where permitted
- Build upload tools
- Build OCR pipeline
- Build text extraction
- Build document storage
- Build metadata extraction
- Build error handling

Deliverables:
- Ingestion pipeline
- OCR service
- Document processing dashboard
- Storage architecture
```

## Workstream C: Legal Structuring and Annotation

```text
Tasks:
- Create legal schemas
- Create issue taxonomy
- Create case-law annotation rules
- Label sample judgments
- Label sample pleadings
- Label relevant/adverse authorities

Deliverables:
- Schema v1
- Annotation guide
- Labeled legal dataset
- Legal taxonomy
```

## Workstream D: Retrieval and Ranking

```text
Tasks:
- Build keyword index
- Build vector index
- Build metadata filters
- Build citation graph
- Build reranker
- Build authority-aware ranking
- Build retrieval explanations

Deliverables:
- Retrieval API
- Search UI
- Reranking model
- Legal research pack generator
```

## Workstream E: Argument and Adversarial Engine

```text
Tasks:
- Build argument templates
- Build element mapper
- Build fact-to-evidence mapper
- Build opponent simulation
- Build counterprecedent search
- Build stress-test scoring

Deliverables:
- Argument builder
- Opponent simulator
- Strategy report generator
```

## Workstream F: User Experience

```text
Tasks:
- Design lawyer workspace
- Design case dashboard
- Design research result cards
- Design argument cards
- Design document viewer
- Design export templates

Deliverables:
- Web app
- Case dashboard
- Argument workspace
- Export center
```

## Workstream G: Evaluation

```text
Tasks:
- Build benchmark cases
- Build annotation workflow
- Measure retrieval quality
- Measure argument quality
- Track hallucinations
- Track missed adverse authorities

Deliverables:
- Evaluation dataset
- Evaluation dashboard
- Error reports
- Production scorecard
```

## Workstream H: Security and Compliance

```text
Tasks:
- Define access control
- Define tenant isolation
- Define audit logging
- Define retention rules
- Define external model policy
- Run security testing

Deliverables:
- Security architecture
- Compliance checklist
- Audit system
- Deployment approval
```

---

# Team Structure

## Core team

```text
Product:
- Product owner
- Legal product manager

Legal:
- Senior Sri Lankan lawyer / legal advisor
- Civil procedure expert
- Criminal procedure expert
- Constitutional / writ expert
- Commercial law expert
- Legal annotators / junior lawyers

Engineering:
- Backend engineers
- Frontend engineers
- Data engineers
- ML / NLP engineers
- DevOps engineer
- Security engineer

Design and QA:
- UX designer
- QA engineer
- Legal QA reviewers
```

## Suggested minimum team for serious build

```text
- 1 product lead
- 1 senior legal lead
- 2-4 legal reviewers / annotators
- 2 backend engineers
- 1 frontend engineer
- 1 data engineer
- 1 ML/NLP engineer
- 1 DevOps/security engineer
- 1 QA engineer
```

---

# Key Risks and Mitigations

| Risk | Why it matters | Mitigation |
|---|---|---|
| Missing legal sources | System may miss important authorities | Source registry, legal review, warnings |
| Copyright/licensing issues | Cannot legally ingest some databases | Licence review before ingestion |
| Hallucinated cases | Dangerous legal output | Citation-first design, validation layer |
| Outdated statutes | Wrong legal advice risk | Version-controlled statutes and amendments |
| Poor OCR | Wrong extraction from old PDFs | OCR confidence, manual review queue |
| Sinhala/Tamil gaps | Incomplete coverage | Multilingual OCR and cross-lingual search |
| Missing adverse cases | Biased or unsafe strategy | Mandatory adverse authority retrieval |
| Overreliance by lawyers | Professional risk | Human approval workflow |
| Confidentiality breach | Severe legal and reputational risk | Tenant isolation, encryption, audit logs |
| Prompt injection | Uploaded docs may manipulate model | Treat documents as data, not instructions |
| Weak evaluation | False confidence in system | Lawyer-labeled benchmarks |

---

# Recommended Build Order

## Stage 1: Build the corpus and retrieval foundation

```text
1. Source registry
2. Document ingestion
3. OCR and parsing
4. Metadata extraction
5. Legal segmentation
6. Search index
7. Vector index
8. Citation graph
9. Authority ranking
```

## Stage 2: Build Part 1

```text
1. Case profile extraction
2. Legal issue extraction
3. Query planner
4. Hybrid search
5. Reranking
6. Legal research pack
7. Lawyer review UI
8. Evaluation benchmark
```

## Stage 3: Build Part 2

```text
1. Argument object schema
2. Element mapping
3. Fact-to-evidence mapping
4. Argument generator
5. Opponent simulation
6. Counterprecedent search
7. Stress testing
8. Strategy report
```

## Stage 4: Productionise

```text
1. Security hardening
2. Audit logging
3. Performance optimisation
4. Cost optimisation
5. Legal QA
6. Pilot programme
7. Controlled launch
8. Continuous updates
```

---

# Final Production Architecture Summary

```text
Legal AI System
│
├── Data Layer
│   ├── Official legal documents
│   ├── Court judgments
│   ├── Procedural rules
│   ├── Gazettes
│   ├── Litigation documents
│   └── User case files
│
├── Processing Layer
│   ├── OCR
│   ├── Text extraction
│   ├── Document classification
│   ├── Legal segmentation
│   ├── Metadata extraction
│   ├── Citation extraction
│   └── Statute versioning
│
├── Knowledge Layer
│   ├── Legal schema
│   ├── Issue taxonomy
│   ├── Citation graph
│   ├── Authority ranking
│   ├── Case treatment labels
│   └── Amendment history
│
├── Retrieval Layer
│   ├── Metadata search
│   ├── Keyword search
│   ├── Semantic search
│   ├── Citation expansion
│   ├── Reranking
│   └── Legal research pack
│
├── Reasoning Layer
│   ├── Case profile extraction
│   ├── Legal issue generation
│   ├── Argument construction
│   ├── Counterargument generation
│   ├── Stress testing
│   └── Impact ranking
│
├── User Layer
│   ├── Lawyer workspace
│   ├── Case dashboard
│   ├── Research viewer
│   ├── Argument builder
│   ├── Strategy report
│   └── Export tools
│
└── Governance Layer
    ├── Human review
    ├── Security
    ├── Audit logging
    ├── Confidentiality controls
    ├── Evaluation
    └── Continuous legal updates
```

---

# Most Important Sequence

The most important product decision is this:

```text
Do not build the argument engine first.

Build the retrieval engine first.

If the retrieval engine is weak, the argument engine will be legally dangerous.
```

Recommended order:

```text
1. Clean legal corpus
2. Structured legal schema
3. Reliable retrieval
4. Authority ranking
5. Adverse authority detection
6. Legal research pack
7. Argument builder
8. Opponent simulation
9. Stress testing
10. Strategy report
```

A strong legal AI system is not primarily a chatbot. It is a **legal data system + retrieval system + reasoning system + lawyer workflow system**.
