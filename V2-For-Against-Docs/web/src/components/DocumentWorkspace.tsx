"use client";

import {
  BookOpen,
  CheckCircle2,
  Download,
  ExternalLink,
  Gavel,
  Loader2,
  Maximize2,
  Network,
  RefreshCw,
  Scale,
  Search,
  Send,
  ShieldCheck,
  TriangleAlert,
  X,
} from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { useMemo, useState, useTransition } from "react";
import { PdfDocumentViewer } from "./PdfDocumentViewer";
import type {
  AgenticResearchPlan,
  AgentToolTrace,
  AuthorityPackExpansionPlan,
  AuthorityExpansionCandidate,
  CaseDocument,
  ClarificationNeed,
  DraftSummary,
  MatterMemory,
  ReasoningPack,
  ResearchPackItem,
  ReviewDecisionInput,
  ReviewItem,
} from "@/lib/workspace-types";

export type WorkspaceTab = "documents" | "pack" | "drafts" | "reasoning" | "review";
type DocumentCategoryId = "all" | "acts" | "gazettes" | "supreme_court" | "court_of_appeal" | "high_court" | "hazards" | "other";
type DocumentCacheOverlay = Partial<CaseDocument>;
type DocumentViewerMode = "text" | "file";

type DocumentWorkspaceProps = {
  activeCaseId: string | null;
  documents: CaseDocument[];
  packItems: ResearchPackItem[];
  drafts: DraftSummary[];
  reviewItems: ReviewItem[];
  selectedDocumentId: string | null;
  selectedPackItemId: string | null;
  activeTab: WorkspaceTab;
  showTabHeader?: boolean;
  showSummaryFooter?: boolean;
  onActiveTabChange: (tab: WorkspaceTab) => void;
  onSelectDocument: (documentId: string) => void;
  onSelectPackItem: (packItemId: string) => void;
  onReviewDecision: (input: ReviewDecisionInput) => Promise<{ ok: true; data: ReviewItem } | { ok: false; error: string }>;
};

export function DocumentWorkspace({
  activeCaseId,
  documents,
  packItems,
  drafts,
  reviewItems,
  selectedDocumentId,
  selectedPackItemId,
  activeTab,
  showTabHeader = true,
  showSummaryFooter = true,
  onActiveTabChange,
  onSelectDocument,
  onSelectPackItem,
  onReviewDecision,
}: DocumentWorkspaceProps) {
  const selectedDocument = documents.find((document) => document.documentId === selectedDocumentId) ?? documents[0] ?? null;
  const selectedPackItem = packItems.find((item) => item.packItemId === selectedPackItemId) ?? packItems[0] ?? null;

  return (
    <main className="flex h-full min-h-0 flex-col bg-[#fcf9f5]" aria-label="Case workspace">
      {showTabHeader ? (
        <header className="flex min-h-12 shrink-0 items-center gap-2 overflow-x-auto border-b border-[#c3c6d6] bg-[#fcf9f5] px-3">
          <TabButton active={activeTab === "documents"} icon={<BookOpen size={16} />} label="Documents" onClick={() => onActiveTabChange("documents")} />
          <TabButton active={activeTab === "pack"} icon={<Scale size={16} />} label="Research Pack" onClick={() => onActiveTabChange("pack")} />
          <TabButton active={activeTab === "reasoning" || activeTab === "drafts"} icon={<Network size={16} />} label="Reasoning" onClick={() => onActiveTabChange("reasoning")} />
          <TabButton active={activeTab === "review"} icon={<ShieldCheck size={16} />} label="Review" onClick={() => onActiveTabChange("review")} />
        </header>
      ) : null}
      {activeTab === "documents" ? (
        <DocumentsTab
          activeCaseId={activeCaseId}
          documents={documents}
          packItems={packItems}
          selectedDocument={selectedDocument}
          onSelectDocument={onSelectDocument}
        />
      ) : null}
      {activeTab === "pack" ? (
        <ResearchPackTab
          packItems={packItems}
          selectedPackItem={selectedPackItem}
          onSelectPackItem={(packItemId) => {
            onSelectPackItem(packItemId);
            const item = packItems.find((candidate) => candidate.packItemId === packItemId);
            if (item) {
              onSelectDocument(item.documentId);
            }
          }}
        />
      ) : null}
      {activeTab === "drafts" || activeTab === "reasoning" ? (
        <ReasoningTab
          drafts={drafts}
          packItems={packItems}
          onOpenPackItem={(packItemId) => {
            onSelectPackItem(packItemId);
            const item = packItems.find((candidate) => candidate.packItemId === packItemId);
            if (item) {
              onSelectDocument(item.documentId);
            }
            onActiveTabChange("pack");
          }}
        />
      ) : null}
      {activeTab === "review" ? <ReviewTab activeCaseId={activeCaseId} reviewItems={reviewItems} onReviewDecision={onReviewDecision} /> : null}
      {showSummaryFooter ? (
        <footer className="grid shrink-0 grid-cols-1 gap-px border-t border-[#c3c6d6] bg-[#c3c6d6] xl:grid-cols-3">
          <SummaryPanel title="Pack Items" value={packItems.length} body={selectedPackItem?.citation || "No cited pack item selected."} onClick={() => onActiveTabChange("pack")} />
          <SummaryPanel title="Reasoning" value={drafts.filter((draft) => draft.reasoningPack).length} body={drafts[0]?.title || "No reasoning pack loaded for this case."} onClick={() => onActiveTabChange("reasoning")} />
          <SummaryPanel title="Review" value={reviewItems.length} body={reviewItems[0]?.itemTitle || "No review items loaded."} onClick={() => onActiveTabChange("review")} />
        </footer>
      ) : null}
    </main>
  );
}

function DocumentsTab({
  activeCaseId,
  documents,
  packItems,
  selectedDocument,
  onSelectDocument,
}: {
  activeCaseId: string | null;
  documents: CaseDocument[];
  packItems: ResearchPackItem[];
  selectedDocument: CaseDocument | null;
  onSelectDocument: (documentId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState<DocumentCategoryId>("all");
  const [viewerDocumentId, setViewerDocumentId] = useState<string | null>(null);
  const [cacheOverlay, setCacheOverlay] = useState<Record<string, DocumentCacheOverlay>>({});
  const [cacheStatus, setCacheStatus] = useState<Record<string, "idle" | "caching" | "failed">>({});
  const [refreshStatus, setRefreshStatus] = useState<Record<string, "idle" | "refreshing" | "failed">>({});
  const [cacheError, setCacheError] = useState<string | null>(null);
  const normalizedQuery = query.trim().toLowerCase();
  const documentsWithCache = useMemo(
    () => documents.map((document) => applyDocumentCacheOverlay(document, cacheOverlay[document.documentId])),
    [cacheOverlay, documents],
  );
  const categoryCounts = useMemo(() => buildDocumentCategoryCounts(documentsWithCache), [documentsWithCache]);
  const filteredDocuments = useMemo(
    () =>
      documentsWithCache.filter((document) => {
        if (!documentMatchesCategory(document, activeCategory)) {
          return false;
        }
        if (!normalizedQuery) {
          return true;
        }
        return documentSearchText(document).includes(normalizedQuery);
      }),
    [activeCategory, documentsWithCache, normalizedQuery],
  );
  const selectedDocumentWithCache = selectedDocument
    ? applyDocumentCacheOverlay(selectedDocument, cacheOverlay[selectedDocument.documentId])
    : filteredDocuments[0] ?? null;
  const viewerDocument =
    documentsWithCache.find((document) => document.documentId === viewerDocumentId) ??
    (viewerDocumentId === selectedDocumentWithCache?.documentId ? selectedDocumentWithCache : null);
  const selectedRelatedPackItems = useMemo(
    () => (selectedDocumentWithCache ? packItems.filter((item) => item.documentId === selectedDocumentWithCache.documentId) : []),
    [packItems, selectedDocumentWithCache],
  );
  const viewerRelatedPackItems = useMemo(
    () => (viewerDocument ? packItems.filter((item) => item.documentId === viewerDocument.documentId) : []),
    [packItems, viewerDocument],
  );

  function openDocument(document: CaseDocument) {
    onSelectDocument(document.documentId);
    setViewerDocumentId(document.documentId);
    setCacheError(null);
  }

  async function cacheDocument(document: CaseDocument) {
    if (!activeCaseId) {
      setCacheError("Open a matter before caching a document file.");
      return;
    }
    setCacheError(null);
    setCacheStatus((current) => ({ ...current, [document.documentId]: "caching" }));
    try {
      const response = await fetch(documentCacheRoute(activeCaseId, document.documentId), { method: "POST" });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
        throw new Error(typeof payload?.detail === "string" ? payload.detail : "Document caching failed.");
      }
      const payload = (await response.json()) as DocumentCacheOverlay;
      setCacheOverlay((current) => ({ ...current, [document.documentId]: payload }));
      setCacheStatus((current) => ({ ...current, [document.documentId]: "idle" }));
    } catch (error) {
      setCacheStatus((current) => ({ ...current, [document.documentId]: "failed" }));
      setCacheError(error instanceof Error ? error.message : "Document caching failed.");
    }
  }

  async function refreshDocument(document: CaseDocument) {
    if (!activeCaseId) {
      setCacheError("Open a matter before refreshing document status.");
      return;
    }
    setCacheError(null);
    setRefreshStatus((current) => ({ ...current, [document.documentId]: "refreshing" }));
    try {
      const response = await fetch(documentStatusRoute(activeCaseId, document.documentId));
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
        throw new Error(typeof payload?.detail === "string" ? payload.detail : "Document status refresh failed.");
      }
      const payload = (await response.json()) as CaseDocument;
      setCacheOverlay((current) => ({ ...current, [document.documentId]: payload }));
      setRefreshStatus((current) => ({ ...current, [document.documentId]: "idle" }));
    } catch (error) {
      setRefreshStatus((current) => ({ ...current, [document.documentId]: "failed" }));
      setCacheError(error instanceof Error ? error.message : "Document status refresh failed.");
    }
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-px overflow-hidden bg-[#c3c6d6] 2xl:grid-cols-[minmax(300px,380px)_1fr]">
      <section className="min-h-0 overflow-y-auto bg-[#fcf9f5]" aria-label="Document list">
        <PanelHeader title="Case files" count={filteredDocuments.length} />
        <nav className="border-b border-[#c3c6d6] p-2.5" aria-label="Document categories">
          <div className="grid grid-cols-2 gap-1">
            {DOCUMENT_CATEGORIES.map((category) => (
              <button
                key={category.id}
                className={`flex h-8 items-center justify-between gap-2 rounded-lg px-2.5 text-left text-[11px] font-bold transition ${
                  activeCategory === category.id ? "bg-[#003d9b] text-white" : "text-[#434654] hover:bg-[#f0edea] hover:text-[#003d9b]"
                }`}
                type="button"
                onClick={() => setActiveCategory(category.id)}
                aria-pressed={activeCategory === category.id}
              >
                <span className="truncate">{category.label}</span>
                <span className={`rounded-md px-1.5 py-0.5 ${activeCategory === category.id ? "bg-white/15" : "bg-[#f0edea] text-[#434654]"}`}>
                  {categoryCounts[category.id]}
                </span>
              </button>
            ))}
          </div>
        </nav>
        <div className="border-b border-[#c3c6d6] p-2.5">
          <label className="flex h-9 items-center gap-2 rounded-lg border border-[#c3c6d6] bg-white px-2.5 text-xs text-[#434654] focus-within:border-[#003d9b] focus-within:ring-2 focus-within:ring-[#003d9b]/10">
            <Search size={15} />
            <span className="sr-only">Search documents</span>
            <input
              className="min-w-0 flex-1 bg-transparent text-[#1c1c1a] outline-none placeholder:text-[#737685]"
              value={query}
              placeholder="Search documents"
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
        </div>
        <div className="space-y-2 p-2.5">
          {filteredDocuments.length === 0 ? (
            <EmptyPanel text="Case documents will appear here with citations, page counts, and source quality flags." />
          ) : (
            filteredDocuments.map((document) => (
              <article
                key={document.documentId}
                className={`w-full rounded-xl border p-3 text-left transition ${
                  document.documentId === selectedDocumentWithCache?.documentId
                    ? "border-[#003d9b] bg-white"
                    : "border-[#c3c6d6] bg-white hover:border-[#003d9b] hover:bg-[#fcf9f5]"
                }`}
              >
                <button className="w-full text-left" type="button" onClick={() => openDocument(document)} aria-label={`Open ${document.title}`}>
                  <span className="block text-xs font-bold text-[#1c1c1a]">{document.title}</span>
                  <span className="mt-1 block text-xs text-[#434654]">{document.citation}</span>
                  <span className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-[#434654]">
                    <span className="inline-flex items-center gap-1">
                      <Gavel size={13} />
                      Authority {document.authorityLevel}
                    </span>
                    <span>{document.pageCount} pages</span>
                    {document.relevanceScore != null ? <span>{formatPercent(document.relevanceScore)} relevant</span> : null}
                    {document.caseFileAvailable ? <span className="font-bold text-emerald-700">Case file</span> : null}
                  </span>
                </button>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <DocumentActionButton icon={<Maximize2 size={14} />} label="View" onClick={() => openDocument(document)} />
                  <DocumentDownloadLink activeCaseId={activeCaseId} document={document} />
                  {!document.caseFileAvailable && hasCacheSource(document) ? (
                    <button
                      className="inline-flex h-8 items-center gap-1 rounded-lg border border-[#c3c6d6] bg-white px-2 text-xs font-bold text-[#434654] hover:border-[#003d9b] hover:text-[#003d9b] disabled:cursor-wait disabled:opacity-60"
                      type="button"
                      onClick={() => cacheDocument(document)}
                      disabled={cacheStatus[document.documentId] === "caching"}
                    >
                      {cacheStatus[document.documentId] === "caching" ? <Loader2 className="animate-spin" size={14} /> : <Download size={14} />}
                      Cache
                    </button>
                  ) : null}
                </div>
              </article>
            ))
          )}
        </div>
      </section>

      <section className="min-h-0 overflow-y-auto bg-white" aria-label="Document viewer">
        {selectedDocumentWithCache ? (
          <DocumentSummary
            document={selectedDocumentWithCache}
            relatedPackItems={selectedRelatedPackItems}
            activeCaseId={activeCaseId}
            onOpenDocument={openDocument}
          />
        ) : (
          <div className="flex h-full items-center justify-center p-6">
            <EmptyPanel text="Select a case document to inspect source text, citation anchors, and quality warnings." />
          </div>
        )}
      </section>
      {viewerDocument ? (
        <DocumentModal
          key={viewerDocument.documentId}
          activeCaseId={activeCaseId}
          document={viewerDocument}
          relatedPackItems={viewerRelatedPackItems}
          cacheStatus={cacheStatus[viewerDocument.documentId] ?? "idle"}
          refreshStatus={refreshStatus[viewerDocument.documentId] ?? "idle"}
          cacheError={cacheError}
          onCacheDocument={cacheDocument}
          onRefreshDocument={refreshDocument}
          onClose={() => setViewerDocumentId(null)}
        />
      ) : null}
    </div>
  );
}

function DocumentSummary({
  document,
  relatedPackItems,
  activeCaseId,
  onOpenDocument,
}: {
  document: CaseDocument;
  relatedPackItems: ResearchPackItem[];
  activeCaseId: string | null;
  onOpenDocument: (document: CaseDocument) => void;
}) {
  const anchorCount = relatedPackItems.reduce((count, item) => count + item.anchors.length, 0);
  return (
      <div className="mx-auto max-w-4xl px-5 py-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase text-slate-500">{document.documentType}</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-950">{document.title}</h2>
          <p className="mt-1 text-xs text-slate-600">{document.citation}</p>
        </div>
        <div className="rounded-md border border-slate-200 px-3 py-2 text-right text-xs text-slate-600">
          <div>{document.pageCount} pages</div>
          <div>{document.sourceId}</div>
        </div>
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <DocumentActionButton icon={<Maximize2 size={15} />} label="Open viewer" onClick={() => onOpenDocument(document)} />
        <DocumentDownloadLink activeCaseId={activeCaseId} document={document} />
      </div>
      {relatedPackItems.length > 0 ? (
        <div className="mb-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
          Related to this case through {relatedPackItems.length} research pack item{relatedPackItems.length === 1 ? "" : "s"} and {anchorCount} citation anchor
          {anchorCount === 1 ? "" : "s"}.
        </div>
      ) : null}
      {document.relevanceScore != null ? (
        <div className="mb-4 grid gap-2 rounded-md border border-slate-200 bg-white p-3 text-xs text-slate-700 sm:grid-cols-3">
          <CompactMetric label="Relevance" value={`${formatPercent(document.relevanceScore)} ${document.relevanceBand ?? ""}`.trim()} />
          <CompactMetric label="Confidence" value={document.confidenceScore != null ? formatPercent(document.confidenceScore) : "Pending"} />
          <CompactMetric label="Reason" value={document.relevanceRationale ?? "Retrieval candidate"} />
        </div>
      ) : null}
      {document.qualityFlags.length > 0 ? (
        <div className="mb-4 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <TriangleAlert className="mt-0.5 shrink-0" size={16} />
          <span>{document.qualityFlags.join(", ")}</span>
        </div>
      ) : (
        <div className="mb-4 flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
          <CheckCircle2 size={16} />
          Source text is available for cited review.
        </div>
      )}
      <article className="min-h-[420px] whitespace-pre-wrap rounded-md border border-slate-200 bg-[#fbfbf8] p-5 font-serif text-sm leading-7 text-slate-950">
        {document.textPreview || "No extracted text preview has been indexed for this document."}
      </article>
    </div>
  );
}

function DocumentModal({
  activeCaseId,
  document,
  relatedPackItems,
  cacheStatus,
  refreshStatus,
  cacheError,
  onCacheDocument,
  onRefreshDocument,
  onClose,
}: {
  activeCaseId: string | null;
  document: CaseDocument;
  relatedPackItems: ResearchPackItem[];
  cacheStatus: "idle" | "caching" | "failed";
  refreshStatus: "idle" | "refreshing" | "failed";
  cacheError: string | null;
  onCacheDocument: (document: CaseDocument) => void;
  onRefreshDocument: (document: CaseDocument) => void;
  onClose: () => void;
}) {
  const fileUrl = activeCaseId && document.caseFileAvailable ? documentFileRoute(activeCaseId, document.documentId) : null;
  const externalUrl = document.downloadUrl || document.sourceUrl || null;
  const hasTextPreview = Boolean(document.textPreview.trim());
  const hasRelatedCaseText = hasTextPreview || relatedPackItems.some((item) => item.anchors.some((anchor) => anchor.quote.trim()));
  const [viewerMode, setViewerMode] = useState<DocumentViewerMode>(hasRelatedCaseText || !fileUrl ? "text" : "file");
  const viewerModeDescription =
    viewerMode === "file"
      ? "Showing the cached case file from the local project route."
      : hasRelatedCaseText
        ? "Showing extracted case text, citation anchors, and document details."
        : "Showing document details; OCR is required for searchable text.";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#1c1c1a]/65 p-4" role="dialog" aria-modal="true" aria-label={`${document.title} viewer`}>
      <div className="flex h-[92dvh] w-full max-w-7xl flex-col overflow-hidden rounded-xl border border-[#c3c6d6] bg-[#fcf9f5] shadow-2xl">
        <header className="flex min-h-16 shrink-0 items-center justify-between gap-3 border-b border-[#c3c6d6] bg-[#fcf9f5]/95 px-6">
          <div className="min-w-0">
            <p className="truncate text-lg font-semibold text-[#1c1c1a]">{document.title}</p>
            <p className="truncate text-sm text-[#434654]">{document.citation}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-[#c3c6d6] bg-white px-3 text-sm font-semibold text-[#434654] transition hover:border-[#003d9b] hover:text-[#003d9b] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#003d9b] disabled:cursor-wait disabled:opacity-60"
              type="button"
              onClick={() => onRefreshDocument(document)}
              disabled={refreshStatus === "refreshing"}
            >
              {refreshStatus === "refreshing" ? <Loader2 className="animate-spin" size={15} /> : <RefreshCw size={15} />}
              Refresh status
            </button>
            <DocumentDownloadLink activeCaseId={activeCaseId} document={document} />
            {!document.caseFileAvailable && hasCacheSource(document) ? (
              <button
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-[#c3c6d6] bg-white px-3 text-sm font-semibold text-[#434654] transition hover:border-[#003d9b] hover:text-[#003d9b] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#003d9b] disabled:cursor-wait disabled:opacity-60"
                type="button"
                onClick={() => onCacheDocument(document)}
                disabled={cacheStatus === "caching"}
              >
                {cacheStatus === "caching" ? <Loader2 className="animate-spin" size={15} /> : <Download size={15} />}
                Cache file
              </button>
            ) : null}
            {externalUrl ? (
              <a
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-[#c3c6d6] bg-white px-3 text-sm font-semibold text-[#434654] transition hover:border-[#003d9b] hover:text-[#003d9b] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#003d9b]"
                href={externalUrl}
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink size={15} />
                Source
              </a>
            ) : null}
            <button
              className="inline-flex size-10 items-center justify-center rounded-lg text-[#434654] transition hover:bg-[#f0edea] hover:text-[#003d9b] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#003d9b]"
              type="button"
              onClick={onClose}
              aria-label="Close document viewer"
            >
              <X size={18} />
            </button>
          </div>
        </header>
        {cacheError ? (
          <div className="border-b border-[#ffb59b] bg-[#ffdbcf] px-6 py-3 text-sm text-[#7b2600]">{cacheError}</div>
        ) : null}
        <div className="flex min-h-0 flex-1 flex-col bg-[#fcf9f5]">
          <section className="shrink-0 border-b border-[#c3c6d6] bg-white/70 px-6 py-4 text-sm" aria-label="Document metadata">
            <div className="flex flex-wrap items-center gap-2">
              <CompactMetric label="Type" value={document.documentType} />
              <CompactMetric label="Authority" value={String(document.authorityLevel)} />
              <CompactMetric label="Pages" value={String(document.pageCount)} />
              <CompactMetric label="Source" value={document.sourceId} />
              {document.qualityFlags.length > 0 ? (
                <span className="inline-flex min-h-9 items-center gap-2 rounded-full border border-[#ffb59b] bg-[#ffdbcf] px-4 py-1 text-[#7b2600]">
                  <TriangleAlert size={15} />
                  {document.qualityFlags.join(", ")}
                </span>
              ) : (
                <span className="inline-flex min-h-9 items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-4 py-1 text-emerald-900">
                  <CheckCircle2 size={15} />
                  Source text indexed
                </span>
              )}
            </div>
          </section>
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-[#c3c6d6] bg-[#fcf9f5] px-6 py-3">
            <div className="inline-flex rounded-xl border border-[#c3c6d6] bg-white p-1" role="group" aria-label="Document viewer mode">
              <ViewerModeButton active={viewerMode === "text"} label="Text" onClick={() => setViewerMode("text")} />
              <ViewerModeButton active={viewerMode === "file"} disabled={!fileUrl} label="File" onClick={() => setViewerMode("file")} />
            </div>
            <p className="text-sm text-[#434654]">{viewerModeDescription}</p>
          </div>
          <section className="min-h-0 flex-1 overflow-hidden bg-[#f6f3ef]" aria-label={viewerMode === "file" ? "Document file preview" : "Document text preview"}>
            {viewerMode === "file" && fileUrl ? (
              <PdfDocumentViewer
                fileUrl={fileUrl}
                title={document.title}
                fallback={<DocumentTextPreview document={document} relatedPackItems={relatedPackItems} />}
              />
            ) : (
              <DocumentTextPreview document={document} relatedPackItems={relatedPackItems} />
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function DocumentTextPreview({ document, relatedPackItems }: { document: CaseDocument; relatedPackItems: ResearchPackItem[] }) {
  const extractedText = document.textPreview.trim();
  const anchorRows = relatedPackItems.flatMap((item) =>
    item.anchors
      .filter((anchor) => anchor.quote.trim())
      .map((anchor) => ({
        anchor,
        item,
      })),
  );
  const needsSearchableText = document.qualityFlags.some((flag) => /ocr|text_empty|text_not_indexed/i.test(flag));
  if (!extractedText && anchorRows.length === 0 && relatedPackItems.length === 0) {
    return (
      <div className="flex h-full items-center justify-center overflow-y-auto bg-[#fcf9f5] p-8">
        <div className="max-w-xl rounded-xl border border-[#ffb59b] bg-white p-6 text-sm leading-6 text-[#434654]">
          <div className="flex items-center gap-2 text-base font-semibold text-[#7b2600]">
            <TriangleAlert size={18} />
            OCR required for searchable text
          </div>
          <p className="mt-3">
            The official document file is stored and viewable in this case, but extracted text has not been produced for this PDF yet.
          </p>
          <dl className="mt-4 grid gap-2 sm:grid-cols-2">
            <CompactMetric label="Document" value={document.citation} />
            <CompactMetric label="Status" value={document.qualityFlags.join(", ") || "text_not_indexed"} />
            <CompactMetric label="Pages" value={String(document.pageCount)} />
            <CompactMetric label="Source" value={document.sourceId} />
          </dl>
          <p className="mt-4 text-[#434654]">Run OCR for this document before relying on the Text tab for search, citations, or strategy generation.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-[#fcf9f5] p-8">
      <div className="mx-auto max-w-6xl space-y-8">
        <section className="rounded-xl border border-[#c3c6d6] bg-white p-6 text-sm leading-6 text-[#434654]">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#434654]">Document details</p>
          <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-2xl font-semibold text-[#1c1c1a]">{document.title}</h3>
              <p className="mt-2 text-base text-[#434654]">{document.citation}</p>
            </div>
            <span className="rounded-lg border border-[#c3c6d6] bg-[#f6f3ef] px-3 py-2 text-sm font-semibold text-[#434654]">{document.documentId}</span>
          </div>
          <dl className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <CompactMetric label="Type" value={document.documentType} />
            <CompactMetric label="Authority" value={String(document.authorityLevel)} />
            <CompactMetric label="Pages" value={String(document.pageCount)} />
            <CompactMetric label="Source" value={document.sourceId} />
            <CompactMetric label="Case file" value={document.caseFileAvailable ? document.caseFileName || "Stored in case folder" : "Not cached"} />
            <CompactMetric label="Quality" value={document.qualityFlags.join(", ") || "Indexed"} />
          </dl>
          {document.localPath || document.sourceUrl || document.downloadUrl ? (
            <div className="mt-6 space-y-2 text-sm text-[#434654]">
              {document.localPath ? <p className="break-words">Local source: {document.localPath}</p> : null}
              {document.sourceUrl ? (
                <p className="break-words">
                  Source URL:{" "}
                  <a className="font-semibold text-[#1c1c1a] underline underline-offset-4" href={document.sourceUrl} target="_blank" rel="noreferrer">
                    {document.sourceUrl}
                  </a>
                </p>
              ) : null}
              {document.downloadUrl ? (
                <p className="break-words">
                  Download URL:{" "}
                  <a className="font-semibold text-[#1c1c1a] underline underline-offset-4" href={document.downloadUrl} target="_blank" rel="noreferrer">
                    {document.downloadUrl}
                  </a>
                </p>
              ) : null}
            </div>
          ) : null}
        </section>

        {needsSearchableText ? (
          <div className="flex items-start gap-3 rounded-xl border border-[#ffb59b] bg-[#fff8e7] p-5 text-base leading-7 text-[#7b2600]">
            <TriangleAlert className="mt-0.5 shrink-0" size={16} />
            <span>Full-page OCR is still required for complete searchable text; this view shows the available case-linked extracted text and citation anchors.</span>
          </div>
        ) : null}

        <section className="rounded-xl border border-[#c3c6d6] bg-white p-6">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#434654]">Case-related extracted text</p>
            <span className="text-sm text-[#434654]">{extractedText ? "Retrieved document text" : "No document-level text returned"}</span>
          </div>
          {extractedText ? (
            <article className="whitespace-pre-wrap rounded-lg border border-[#e5e2de] bg-[#fcf9f5] p-6 font-serif text-xl leading-9 text-[#1c1c1a]">
              {extractedText}
            </article>
          ) : (
            <EmptyPanel text="No document-level text segment is available for this case yet. Review the citation anchors below and run OCR for complete text." />
          )}
        </section>

        <section className="rounded-xl border border-[#c3c6d6] bg-white p-6">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#434654]">Research pack anchors</p>
            <span className="text-sm text-[#434654]">
              {relatedPackItems.length} pack item{relatedPackItems.length === 1 ? "" : "s"} | {anchorRows.length} anchor{anchorRows.length === 1 ? "" : "s"}
            </span>
          </div>
          {relatedPackItems.length === 0 ? (
            <EmptyPanel text="This document is not linked to a research pack item for the active case." />
          ) : (
            <div className="space-y-3">
              {relatedPackItems.map((item) => (
                <article key={item.packItemId} className="rounded-lg border border-[#c3c6d6] p-4 text-sm leading-6 text-[#434654] transition hover:border-[#003d9b]">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-base font-semibold text-[#1c1c1a]">{item.citation}</p>
                      <p className="text-xs text-[#434654]">{item.packItemId}</p>
                    </div>
                    <span className="rounded-lg border border-[#c3c6d6] bg-[#fcf9f5] px-3 py-1 text-sm text-[#434654]">Score {item.fusedScore.toFixed(3)}</span>
                  </div>
                  <p className="mt-2 text-[#434654]">{item.selectionReason}</p>
                  {item.sourceWarnings.length > 0 ? (
                    <div className="mt-2 rounded-lg border border-[#ffb59b] bg-[#fff8e7] px-3 py-2 text-xs text-[#7b2600]">{item.sourceWarnings.join(", ")}</div>
                  ) : null}
                  <div className="mt-3 space-y-2">
                    {item.anchors.length === 0 ? (
                      <EmptyPanel text="No page anchor is available for this cited pack item." />
                    ) : (
                      item.anchors.map((anchor) => (
                        <div key={anchor.anchorId} className="rounded-lg border border-[#e5e2de] bg-[#f6f3ef] p-3">
                          <p className="text-xs text-[#434654]">
                            Page {anchor.pageNumber ?? "unknown"} | Confidence {Math.round(anchor.confidence * 100)}%
                          </p>
                          <blockquote className="mt-1 text-[#1c1c1a]">{anchor.quote}</blockquote>
                        </div>
                      ))
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function ViewerModeButton({ active, disabled = false, label, onClick }: { active: boolean; disabled?: boolean; label: string; onClick: () => void }) {
  return (
    <button
      className={`h-8 rounded-lg px-3 text-xs font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#003d9b] disabled:cursor-not-allowed disabled:opacity-40 ${
        active ? "bg-[#003d9b] text-white" : "text-[#434654] hover:bg-[#f0edea] hover:text-[#003d9b]"
      }`}
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
    >
      {label}
    </button>
  );
}

function CompactMetric({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex min-h-8 max-w-full items-center gap-2 rounded-lg border border-[#e1e1df] bg-white px-3 py-1.5 text-xs">
      <span className="shrink-0 text-[#667085]">{label}</span>
      <span className="min-w-0 break-words font-semibold text-[#1c1c1a]">{value}</span>
    </span>
  );
}

function formatPercent(value: number): string {
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

const DOCUMENT_CATEGORIES: Array<{ id: DocumentCategoryId; label: string }> = [
  { id: "all", label: "All" },
  { id: "acts", label: "Acts" },
  { id: "gazettes", label: "Gazettes" },
  { id: "supreme_court", label: "Supreme Court" },
  { id: "court_of_appeal", label: "Court of Appeal" },
  { id: "high_court", label: "High Court" },
  { id: "hazards", label: "Hazards" },
  { id: "other", label: "Other" },
];

function buildDocumentCategoryCounts(documents: CaseDocument[]): Record<DocumentCategoryId, number> {
  return DOCUMENT_CATEGORIES.reduce(
    (counts, category) => {
      counts[category.id] = documents.filter((document) => documentMatchesCategory(document, category.id)).length;
      return counts;
    },
    {} as Record<DocumentCategoryId, number>,
  );
}

function documentMatchesCategory(document: CaseDocument, category: DocumentCategoryId): boolean {
  const text = documentSearchText(document);
  if (category === "all") {
    return true;
  }
  if (category === "hazards") {
    return document.qualityFlags.length > 0 || (!document.caseFileAvailable && !hasCacheSource(document));
  }
  if (category === "acts") {
    return /\b(act|ordinance|statute|legislation|code)\b/.test(text);
  }
  if (category === "gazettes") {
    return /\b(gazette|extraordinary)\b/.test(text);
  }
  if (category === "supreme_court") {
    return /\b(supreme court|sc\.?|s\.c\.)\b/.test(text);
  }
  if (category === "court_of_appeal") {
    return /\b(court of appeal|appeal court|ca\.?|c\.a\.)\b/.test(text);
  }
  if (category === "high_court") {
    return /\b(high court|commercial high court|provincial high court|hc\.?|h\.c\.)\b/.test(text);
  }
  return !DOCUMENT_CATEGORIES.some((candidate) => candidate.id !== "all" && candidate.id !== "other" && documentMatchesCategory(document, candidate.id));
}

function documentSearchText(document: CaseDocument): string {
  return [document.title, document.citation, document.documentType, document.sourceId, document.sourceUrl, document.downloadUrl]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function applyDocumentCacheOverlay(document: CaseDocument, overlay?: DocumentCacheOverlay): CaseDocument {
  if (!overlay) {
    return document;
  }
  return {
    ...document,
    ...overlay,
    caseFileAvailable: overlay.caseFileAvailable ?? document.caseFileAvailable,
  };
}

function hasCacheSource(document: CaseDocument): boolean {
  return Boolean(document.localPath || document.sourceUrl || document.downloadUrl);
}

function documentFileRoute(caseId: string, documentId: string): string {
  return `/api/cases/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(documentId)}/file`;
}

function documentCacheRoute(caseId: string, documentId: string): string {
  return `/api/cases/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(documentId)}/cache`;
}

function documentStatusRoute(caseId: string, documentId: string): string {
  return `/api/cases/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(documentId)}/status`;
}

function DocumentActionButton({ icon, label, onClick }: { icon: ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      className="inline-flex h-7 items-center gap-1 rounded-lg border border-[#c3c6d6] bg-white px-2 text-[11px] font-bold text-[#434654] transition hover:border-[#003d9b] hover:text-[#003d9b]"
      type="button"
      onClick={onClick}
    >
      {icon}
      {label}
    </button>
  );
}

function DocumentDownloadLink({ activeCaseId, document }: { activeCaseId: string | null; document: CaseDocument }) {
  const localUrl = activeCaseId && document.caseFileAvailable ? documentFileRoute(activeCaseId, document.documentId) : null;
  const externalUrl = document.downloadUrl || document.sourceUrl || null;
  const href = localUrl || externalUrl;
  if (!href) {
    return (
      <span className="inline-flex h-10 items-center gap-2 rounded-lg border border-[#c3c6d6] bg-white px-3 text-sm font-semibold text-[#98a2b3]">
        <Download size={14} />
        Download
      </span>
    );
  }
  return (
    <a
      className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-[#c3c6d6] bg-white px-2.5 text-xs font-semibold text-[#434654] transition hover:border-[#003d9b] hover:text-[#003d9b] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#003d9b]"
      href={href}
      download={localUrl ? document.caseFileName || document.title : undefined}
      target={localUrl ? undefined : "_blank"}
      rel={localUrl ? undefined : "noreferrer"}
    >
      <Download size={14} />
      Download
    </a>
  );
}

function ResearchPackTab({
  packItems,
  selectedPackItem,
  onSelectPackItem,
}: {
  packItems: ResearchPackItem[];
  selectedPackItem: ResearchPackItem | null;
  onSelectPackItem: (packItemId: string) => void;
}) {
  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-px overflow-hidden bg-slate-200 2xl:grid-cols-[minmax(260px,340px)_1fr]">
      <section className="min-h-0 overflow-y-auto bg-white" aria-label="Research pack list">
        <PanelHeader title="Research pack" count={packItems.length} />
        <div className="space-y-1 p-2">
          {packItems.length === 0 ? (
            <EmptyPanel text="Retrieved authorities will appear here as cited pack items." />
          ) : (
            packItems.map((item) => (
              <button
                key={item.packItemId}
                className={`w-full rounded-md border p-3 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-950 ${
                  item.packItemId === selectedPackItem?.packItemId
                    ? "border-slate-400 bg-slate-50"
                    : "border-transparent hover:border-slate-200 hover:bg-slate-50"
                }`}
                type="button"
                onClick={() => onSelectPackItem(item.packItemId)}
              >
                <span className="block text-sm font-semibold text-slate-950">{item.packItemId}</span>
                <span className="mt-1 block text-xs text-slate-500">{item.citation}</span>
              </button>
            ))
          )}
        </div>
      </section>
      <section className="min-h-0 overflow-y-auto bg-white" aria-label="Research pack detail">
        {selectedPackItem ? (
          <div className="mx-auto max-w-3xl space-y-5 px-6 py-6">
            <div>
              <p className="text-xs font-medium uppercase text-slate-500">{selectedPackItem.packId}</p>
              <h2 className="mt-1 text-xl font-semibold text-slate-950">{selectedPackItem.title}</h2>
              <p className="mt-1 text-sm text-slate-600">{selectedPackItem.citation}</p>
            </div>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <Metric label="Authority" value={String(selectedPackItem.authorityLevel)} />
              <Metric label="Score" value={selectedPackItem.fusedScore.toFixed(3)} />
            </dl>
            <div className="rounded-md border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-800">
              {selectedPackItem.selectionReason}
            </div>
            <div>
              <p className="mb-2 text-xs font-medium uppercase text-slate-500">Anchors</p>
              <div className="space-y-2">
                {selectedPackItem.anchors.length === 0 ? (
                  <EmptyPanel text="No page anchor is available for this pack item." />
                ) : (
                  selectedPackItem.anchors.map((anchor) => (
                    <div key={anchor.anchorId} className="rounded-md border border-slate-200 p-3 text-sm">
                      <p className="text-xs text-slate-500">
                        Page {anchor.pageNumber ?? "unknown"} | Confidence {Math.round(anchor.confidence * 100)}%
                      </p>
                      <p className="mt-1 text-slate-950">{anchor.quote}</p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center p-6">
            <EmptyPanel text="Select a research pack item to inspect citation evidence." />
          </div>
        )}
      </section>
    </div>
  );
}

function ReasoningTab({
  drafts,
  packItems,
  onOpenPackItem,
}: {
  drafts: DraftSummary[];
  packItems: ResearchPackItem[];
  onOpenPackItem: (packItemId: string) => void;
}) {
  const [selectedDraftId, setSelectedDraftId] = useState(drafts[0]?.draftId ?? null);
  const selectedDraft = drafts.find((draft) => draft.draftId === selectedDraftId) ?? drafts[0] ?? null;
  const selectedPack = selectedDraft?.reasoningPack ?? null;
  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-px overflow-hidden bg-[#c3c6d6] 2xl:grid-cols-[minmax(280px,360px)_1fr]">
      <section className="min-h-0 overflow-y-auto bg-white" aria-label="Reasoning pack list">
        <PanelHeader title="Reasoning packs" count={drafts.length} />
        <div className="space-y-1 p-2">
          {drafts.length === 0 ? (
            <EmptyPanel text="Pack-bounded reasoning drafts will appear here after generation." />
          ) : (
            drafts.map((draft) => (
              <button
                key={draft.draftId}
                className={`w-full rounded-md border p-3 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-950 ${
                  draft.draftId === selectedDraft?.draftId ? "border-slate-400 bg-slate-50" : "border-transparent hover:border-slate-200 hover:bg-slate-50"
                }`}
                type="button"
                onClick={() => setSelectedDraftId(draft.draftId)}
              >
                <span className="block text-sm font-semibold text-slate-950">{draft.title}</span>
                <span className="mt-1 block text-xs text-slate-500">
                  {draft.requestedOutput ?? draft.draftType} | {draft.status}
                </span>
                {draft.reasoningPack ? (
                  <span className="mt-2 flex flex-wrap gap-1">
                    <StatusPill tone="blue">{draft.reasoningPack.issue_matrix.length} issues</StatusPill>
                    <StatusPill tone="rose">{draft.reasoningPack.missing_evidence_checklist.length} missing</StatusPill>
                    {draft.agenticResearchPlan ? <StatusPill tone="green">{draft.agenticResearchPlan.tool_traces.length} tools</StatusPill> : null}
                  </span>
                ) : null}
              </button>
            ))
          )}
        </div>
      </section>
      <section className="min-h-0 overflow-y-auto bg-white" aria-label="Reasoning pack detail">
        {selectedDraft ? (
          <div className="mx-auto max-w-5xl space-y-5 px-5 py-5">
            <header className="border-b border-[#c3c6d6] pb-4">
              <p className="text-xs font-bold uppercase text-[#434654]">{selectedDraft.requestedOutput ?? selectedDraft.draftType}</p>
              <h2 className="mt-1 text-2xl font-semibold text-[#1c1c1a]">{selectedDraft.title}</h2>
              <div className="mt-3 flex flex-wrap gap-2">
                <StatusPill tone="blue">{selectedDraft.claimCount} claims</StatusPill>
                <StatusPill tone="neutral">Review {selectedDraft.reviewStatus ?? "open"}</StatusPill>
                {selectedPack ? <StatusPill tone="green">{selectedPack.schema_version}</StatusPill> : null}
                {selectedDraft.agenticResearchPlan ? <StatusPill tone="blue">{selectedDraft.agenticResearchPlan.schema_version}</StatusPill> : null}
              </div>
            </header>

            {selectedDraft.agenticResearchPlan || selectedDraft.matterMemory ? (
              <AgenticResearchDetail
                plan={selectedDraft.agenticResearchPlan ?? null}
                memory={selectedDraft.matterMemory ?? null}
                expansionPlans={selectedDraft.authorityPackExpansionPlans ?? []}
                packItems={packItems}
                onOpenPackItem={onOpenPackItem}
              />
            ) : null}

            {selectedPack ? (
              <ReasoningPackDetail pack={selectedPack} packItems={packItems} onOpenPackItem={onOpenPackItem} />
            ) : (
              <article className="min-h-[420px] whitespace-pre-wrap rounded-md border border-slate-200 bg-white p-5 text-sm leading-7 text-slate-900">
                {selectedDraft.contentPreview}
              </article>
            )}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center p-6">
            <EmptyPanel text="Select a reasoning pack to inspect its cited content." />
          </div>
        )}
      </section>
    </div>
  );
}

function AgenticResearchDetail({
  plan,
  memory,
  expansionPlans,
  packItems,
  onOpenPackItem,
}: {
  plan: AgenticResearchPlan | null;
  memory: MatterMemory | null;
  expansionPlans: AuthorityPackExpansionPlan[];
  packItems: ResearchPackItem[];
  onOpenPackItem: (packItemId: string) => void;
}) {
  const traces = plan?.tool_traces ?? memory?.tool_traces ?? [];
  const clarificationNeeds = plan?.clarification_needs ?? memory?.clarification_needs ?? [];
  const candidates = plan?.authority_candidates ?? memory?.candidate_authorities ?? [];
  const promotedPackItemIds = candidates.flatMap((candidate) => candidate.promoted_pack_item_ids);

  return (
    <section className="space-y-4 rounded-md border border-[#c3c6d6] bg-[#f8fbff] p-4" aria-label="Agentic research workflow">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase text-[#003d9b]">Agentic workflow</p>
          <h3 className="mt-1 text-lg font-semibold text-[#1c1c1a]">Tool route and matter memory</h3>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[#434654]">
            {plan?.reviewer_summary ?? "Matter memory is available for this draft."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusPill tone="blue">{traces.length} tool steps</StatusPill>
          <StatusPill tone={clarificationNeeds.some((need) => need.blocks_preliminary_opinion) ? "rose" : "green"}>
            {clarificationNeeds.length} clarifications
          </StatusPill>
          <StatusPill tone="neutral">{candidates.length} candidates</StatusPill>
          {expansionPlans.length ? <StatusPill tone="blue">{expansionPlans.length} expansion plans</StatusPill> : null}
        </div>
      </div>

      <section className="grid gap-3 xl:grid-cols-3" aria-label="Agentic metrics">
        <Metric label="Sealed packs" value={String(memory?.sealed_pack_ids.length ?? 0)} />
        <Metric label="Adverse memory" value={String(memory?.adverse_material.length ?? 0)} />
        <Metric label="Missing tasks" value={String(memory?.missing_evidence_tasks.length ?? 0)} />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <ReasoningSection title="Tool route" count={traces.length}>
          <div className="space-y-2">
            {traces.map((trace, index) => (
              <ToolTraceRow key={trace.trace_id} index={index + 1} trace={trace} />
            ))}
          </div>
        </ReasoningSection>

        <ReasoningSection title="Clarification needs" count={clarificationNeeds.length}>
          {clarificationNeeds.length === 0 ? (
            <EmptyPanel text="No clarification blockers were recorded for this draft." />
          ) : (
            <div className="space-y-2">
              {clarificationNeeds.map((need) => (
                <ClarificationCard key={need.clarification_id} need={need} />
              ))}
            </div>
          )}
        </ReasoningSection>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <ReasoningSection title="Authority candidates" count={candidates.length}>
          {candidates.length === 0 ? (
            <EmptyPanel text="No wider authority candidates were recorded." />
          ) : (
            <div className="space-y-2">
              {candidates.map((candidate) => (
                <AuthorityCandidateCard key={candidate.candidate_id} candidate={candidate} packItems={packItems} onOpenPackItem={onOpenPackItem} />
              ))}
            </div>
          )}
        </ReasoningSection>

        <ReasoningSection title="Matter memory" count={(memory?.client_facts.length ?? 0) + (memory?.missing_evidence_tasks.length ?? 0)}>
          {memory ? (
            <div className="space-y-3">
              <ListBlock title="Client position" values={memory.client_position ? [memory.client_position] : []} tone="blue" />
              <ListBlock title="Client facts" values={memory.client_facts.slice(0, 4)} />
              <ListBlock title="Adverse material" values={memory.adverse_material.slice(0, 4)} tone="rose" />
              <ListBlock title="Missing tasks" values={memory.missing_evidence_tasks.slice(0, 6)} tone="blue" />
              <PackItemButtons packItemIds={promotedPackItemIds} packItems={packItems} onOpenPackItem={onOpenPackItem} />
            </div>
          ) : (
            <EmptyPanel text="Matter memory has not been recorded for this draft." />
          )}
        </ReasoningSection>
      </section>

      {expansionPlans.length ? (
        <ReasoningSection title="Authority expansion plans" count={expansionPlans.length}>
          <div className="space-y-2">
            {expansionPlans.map((expansionPlan) => (
              <AuthorityExpansionPlanCard key={expansionPlan.plan_id} expansionPlan={expansionPlan} />
            ))}
          </div>
        </ReasoningSection>
      ) : null}
    </section>
  );
}

function ToolTraceRow({ index, trace }: { index: number; trace: AgentToolTrace }) {
  return (
    <article className="rounded-md border border-[#c3c6d6] bg-white p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase text-[#434654]">
            Step {index} | {trace.source_boundary}
          </p>
          <h4 className="mt-1 truncate text-sm font-bold text-[#1c1c1a]">{trace.tool_name}</h4>
        </div>
        <StatusPill tone={trace.status === "completed" ? "green" : trace.status === "failed" ? "rose" : "blue"}>{trace.status}</StatusPill>
      </div>
      <p className="mt-2 text-xs leading-5 text-[#434654]">{trace.purpose}</p>
      <p className="mt-2 text-xs leading-5 text-[#1c1c1a]">{trace.reviewer_note}</p>
      <div className="mt-3">
        <Metric label="Results" value={trace.result_count == null ? "planned" : String(trace.result_count)} />
      </div>
    </article>
  );
}

function ClarificationCard({ need }: { need: ClarificationNeed }) {
  return (
    <article className={`rounded-md border p-3 ${need.blocks_preliminary_opinion ? "border-[#f0c7c7] bg-[#fff7f7]" : "border-[#c3c6d6] bg-white"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase text-[#434654]">{need.category}</p>
        <StatusPill tone={need.blocks_preliminary_opinion ? "rose" : "blue"}>
          {need.blocks_preliminary_opinion ? "blocks opinion" : "review"}
        </StatusPill>
      </div>
      <h4 className="mt-2 text-sm font-bold text-[#1c1c1a]">{need.question}</h4>
      <p className="mt-2 text-xs leading-5 text-[#434654]">{need.reason}</p>
    </article>
  );
}

function AuthorityCandidateCard({
  candidate,
  packItems,
  onOpenPackItem,
}: {
  candidate: AuthorityExpansionCandidate;
  packItems: ResearchPackItem[];
  onOpenPackItem: (packItemId: string) => void;
}) {
  const isPromoted = candidate.status === "promoted_to_sealed_pack" && candidate.promoted_pack_item_ids.length > 0;
  return (
    <article className="rounded-md border border-[#c3c6d6] bg-white p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-xs font-bold uppercase text-[#434654]">{candidate.authority_type}</p>
          <h4 className="mt-1 text-sm font-bold text-[#1c1c1a]">{candidate.title}</h4>
        </div>
        <StatusPill tone={isPromoted ? "green" : "blue"}>{candidate.status}</StatusPill>
      </div>
      <p className="mt-2 text-xs leading-5 text-[#434654]">{candidate.citation_or_identifier}</p>
      <p className="mt-2 text-xs leading-5 text-[#1c1c1a]">{candidate.reviewer_note}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <StatusPill tone="neutral">{candidate.verification_status}</StatusPill>
        <StatusPill tone="neutral">{candidate.source_boundary}</StatusPill>
      </div>
      <PackItemButtons packItemIds={candidate.promoted_pack_item_ids} packItems={packItems} onOpenPackItem={onOpenPackItem} />
    </article>
  );
}

function AuthorityExpansionPlanCard({ expansionPlan }: { expansionPlan: AuthorityPackExpansionPlan }) {
  return (
    <article className="rounded-md border border-[#c3c6d6] bg-white p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-xs font-bold uppercase text-[#434654]">{expansionPlan.schema_version}</p>
          <h4 className="mt-1 text-sm font-bold text-[#1c1c1a]">{expansionPlan.plan_id}</h4>
        </div>
        <StatusPill tone={expansionPlan.citable ? "rose" : "blue"}>{expansionPlan.status}</StatusPill>
      </div>
      <p className="mt-2 text-xs leading-5 text-[#434654]">{expansionPlan.reviewer_note}</p>
      <div className="mt-3 grid gap-2 md:grid-cols-2">
        {expansionPlan.expansion_requests.map((request, index) => (
          <div key={`${expansionPlan.plan_id}-${index}`} className="rounded-md border border-[#d8dbe7] bg-[#fbfcff] p-2">
            <p className="text-xs font-bold uppercase text-[#003d9b]">{request.query_class}</p>
            <p className="mt-1 text-xs leading-5 text-[#1c1c1a]">{request.query}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <StatusPill tone={request.filters.require_official ? "green" : "rose"}>
                {request.filters.require_official ? "official required" : "official missing"}
              </StatusPill>
              <StatusPill tone="neutral">{request.max_pack_items} items</StatusPill>
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}

function ReasoningPackDetail({
  pack,
  packItems,
  onOpenPackItem,
}: {
  pack: ReasoningPack;
  packItems: ResearchPackItem[];
  onOpenPackItem: (packItemId: string) => void;
}) {
  return (
    <div className="space-y-5">
      <section className="grid gap-3 xl:grid-cols-3" aria-label="Reasoning pack summary">
        <Metric label="Issues" value={String(pack.issue_matrix.length)} />
        <Metric label="Arguments" value={String(pack.for_against_brief.length)} />
        <Metric label="Missing evidence" value={String(pack.missing_evidence_checklist.length)} />
      </section>

      <section className="rounded-md border border-[#c3c6d6] bg-[#fcf9f5] p-4" aria-label="Preliminary opinion">
        <h3 className="text-sm font-extrabold text-[#1c1c1a]">Preliminary opinion</h3>
        <p className="mt-2 text-sm leading-6 text-[#434654]">{pack.preliminary_legal_opinion.important_qualification}</p>
        <p className="mt-3 text-sm leading-6 text-[#1c1c1a]">{pack.preliminary_legal_opinion.preliminary_opinion}</p>
        <p className="mt-3 text-sm leading-6 text-[#1c1c1a]">{pack.preliminary_legal_opinion.conclusion}</p>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <ReasoningSection title="Issue matrix" count={pack.issue_matrix.length}>
          {pack.issue_matrix.map((issue) => (
            <article key={issue.issue_id} className="rounded-md border border-[#c3c6d6] bg-white p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="text-sm font-bold text-[#1c1c1a]">{issue.issue}</h3>
                <StatusPill tone="neutral">{Math.round(issue.confidence * 100)}%</StatusPill>
              </div>
              <p className="mt-1 text-xs font-medium text-[#434654]">{issue.legal_area}</p>
              <div className="mt-3 space-y-2">
                {issue.elements.map((element) => (
                  <div key={element.element_id} className="rounded-md bg-[#f6f3ef] p-2 text-xs leading-5 text-[#1c1c1a]">
                    <p className="font-bold">{element.element}</p>
                    <ListLine label="For" values={element.supporting_facts} />
                    <ListLine label="Against" values={element.opposing_facts} />
                    <PackItemButtons packItemIds={element.pack_item_ids} packItems={packItems} onOpenPackItem={onOpenPackItem} />
                  </div>
                ))}
              </div>
            </article>
          ))}
        </ReasoningSection>

        <ReasoningSection title="For and against" count={pack.for_against_brief.length}>
          {pack.for_against_brief.map((argument) => (
            <article key={argument.issue_id} className="rounded-md border border-[#c3c6d6] bg-white p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-bold text-[#1c1c1a]">{argument.issue}</h3>
                <StatusPill tone={argument.strength === "high" ? "green" : argument.strength === "low" ? "rose" : "blue"}>{argument.strength}</StatusPill>
              </div>
              <ListBlock title="For" values={[argument.client_argument]} />
              <ListBlock title="Against" values={[argument.opposing_argument]} tone="rose" />
              <ListBlock title="Rebuttal" values={[argument.rebuttal]} tone="blue" />
              <ListBlock title="Weaknesses" values={argument.weaknesses} tone="rose" />
              <PackItemButtons packItemIds={argument.pack_item_ids} packItems={packItems} onOpenPackItem={onOpenPackItem} />
            </article>
          ))}
        </ReasoningSection>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <ReasoningSection title="Fact-to-law mapping" count={pack.fact_to_law_mappings.length}>
          {pack.fact_to_law_mappings.map((mapping, index) => (
            <article key={`${mapping.issue_id}-${index}`} className="rounded-md border border-[#c3c6d6] bg-white p-3">
              <p className="text-xs font-bold uppercase text-[#434654]">{mapping.issue_id}</p>
              <h3 className="mt-1 text-sm font-bold text-[#1c1c1a]">{mapping.legal_question}</h3>
              <p className="mt-2 text-xs leading-5 text-[#1c1c1a]">{mapping.fact}</p>
              <p className="mt-2 text-xs leading-5 text-[#434654]">{mapping.supporting_reasoning}</p>
              <ListBlock title="Risk" values={[mapping.risk]} tone="rose" />
              <PackItemButtons packItemIds={mapping.pack_item_ids} packItems={packItems} onOpenPackItem={onOpenPackItem} />
            </article>
          ))}
        </ReasoningSection>

        <ReasoningSection title="Missing evidence" count={pack.missing_evidence_checklist.length}>
          <ul className="space-y-2">
            {pack.missing_evidence_checklist.map((item) => (
              <li key={item} className="rounded-md border border-[#f0c7c7] bg-[#fff7f7] p-3 text-sm leading-6 text-[#7f1d1d]">
                {item}
              </li>
            ))}
          </ul>
          <ListBlock title="Questions for client" values={pack.lawyer_review_pack.questions_for_client} tone="blue" />
          <ListBlock title="Questions for lawyer" values={pack.lawyer_review_pack.questions_for_lawyer} tone="green" />
        </ReasoningSection>
      </section>

      <ReasoningSection title="Authority verification" count={pack.authority_verifications.length}>
        <div className="grid gap-3 xl:grid-cols-2">
          {pack.authority_verifications.map((authority) => (
            <article key={authority.authority_id} className="rounded-md border border-[#c3c6d6] bg-white p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="text-sm font-bold text-[#1c1c1a]">{authority.title}</h3>
                  <p className="mt-1 text-xs text-[#434654]">{authority.citation}</p>
                </div>
                <StatusPill tone={authority.verification_status === "verified" ? "green" : "blue"}>{authority.verification_status}</StatusPill>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
                <Metric label="Official source" value={authority.official_source_checked ? "checked" : "review"} />
                <Metric label="Amendments" value={authority.amendment_checked ? "checked" : "review"} />
              </dl>
              <p className="mt-3 text-xs leading-5 text-[#434654]">{authority.notes}</p>
              <PackItemButtons packItemIds={authority.pack_item_ids} packItems={packItems} onOpenPackItem={onOpenPackItem} />
            </article>
          ))}
        </div>
      </ReasoningSection>
    </div>
  );
}

function ReviewTab({
  activeCaseId,
  reviewItems,
  onReviewDecision,
}: {
  activeCaseId: string | null;
  reviewItems: ReviewItem[];
  onReviewDecision: (input: ReviewDecisionInput) => Promise<{ ok: true; data: ReviewItem } | { ok: false; error: string }>;
}) {
  const [selectedReviewId, setSelectedReviewId] = useState(reviewItems[0]?.reviewItemId ?? null);
  const selectedReview = reviewItems.find((item) => item.reviewItemId === selectedReviewId) ?? reviewItems[0] ?? null;
  const [comment, setComment] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function submitDecision(decision: ReviewDecisionInput["decision"]) {
    if (!activeCaseId || !selectedReview) {
      setMessage("Open a matter and select a review item.");
      return;
    }
    setMessage(null);
    startTransition(async () => {
      const result = await onReviewDecision({
        caseId: activeCaseId,
        reviewItemId: selectedReview.reviewItemId,
        decision,
        comment,
      });
      if (result.ok) {
        setMessage(`Review ${result.data.status}.`);
        setComment("");
      } else {
        setMessage(result.error);
      }
    });
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-px overflow-hidden bg-[#c3c6d6] 2xl:grid-cols-[minmax(280px,360px)_1fr]">
      <section className="min-h-0 overflow-y-auto bg-white" aria-label="Review queue">
        <PanelHeader title="Review queue" count={reviewItems.length} />
        <div className="space-y-1 p-2">
          {reviewItems.length === 0 ? (
            <EmptyPanel text="Draft and claim review tasks will appear here for lawyer approval." />
          ) : (
            reviewItems.map((item) => (
              <button
                key={item.reviewItemId}
                className={`w-full rounded-md border p-3 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-950 ${
                  item.reviewItemId === selectedReview?.reviewItemId ? "border-slate-400 bg-slate-50" : "border-transparent hover:border-slate-200 hover:bg-slate-50"
                }`}
                type="button"
                onClick={() => setSelectedReviewId(item.reviewItemId)}
              >
                <span className="block text-sm font-semibold text-slate-950">{item.itemTitle}</span>
                <span className="mt-1 block text-xs text-slate-500">
                  {item.itemType} | {item.priority}
                </span>
                <span className="mt-2 inline-flex">
                  <StatusPill tone={item.status === "approved" ? "green" : item.status === "changes_requested" || item.status === "rejected" ? "rose" : "blue"}>{item.status}</StatusPill>
                </span>
              </button>
            ))
          )}
        </div>
      </section>
      <section className="min-h-0 overflow-y-auto bg-white" aria-label="Review detail">
        {selectedReview ? (
          <div className="mx-auto max-w-3xl space-y-4 px-6 py-6">
            <p className="text-xs font-medium uppercase text-slate-500">{selectedReview.itemType}</p>
            <h2 className="text-xl font-semibold text-slate-950">{selectedReview.itemTitle}</h2>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <Metric label="Status" value={selectedReview.status} />
              <Metric label="Priority" value={selectedReview.priority} />
            </dl>
            <form
              className="space-y-3 rounded-md border border-[#c3c6d6] bg-[#fcf9f5] p-4"
              onSubmit={(event: FormEvent<HTMLFormElement>) => event.preventDefault()}
            >
              <label className="block text-sm font-medium text-[#1c1c1a]">
                Review comment
                <textarea
                  className="mt-2 min-h-24 w-full resize-none rounded-md border border-[#c3c6d6] bg-white px-3 py-2 text-sm leading-6 outline-none focus:border-[#003d9b] focus:ring-2 focus:ring-[#003d9b]/10"
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                />
              </label>
              {message ? <p className="text-sm text-[#434654]">{message}</p> : null}
              <div className="flex flex-wrap gap-2">
                <button
                  className="inline-flex h-9 items-center gap-2 rounded-md bg-[#0f766e] px-3 text-sm font-bold text-white hover:bg-[#115e59] disabled:bg-slate-300"
                  type="button"
                  disabled={isPending}
                  onClick={() => submitDecision("approved")}
                >
                  <CheckCircle2 size={16} />
                  Approve
                </button>
                <button
                  className="inline-flex h-9 items-center gap-2 rounded-md bg-[#003d9b] px-3 text-sm font-bold text-white hover:bg-[#002d73] disabled:bg-slate-300"
                  type="button"
                  disabled={isPending}
                  onClick={() => submitDecision("changes_requested")}
                >
                  <Send size={16} />
                  Request changes
                </button>
                <button
                  className="inline-flex h-9 items-center gap-2 rounded-md border border-[#c3c6d6] bg-white px-3 text-sm font-bold text-[#7f1d1d] hover:border-[#7f1d1d] disabled:text-slate-400"
                  type="button"
                  disabled={isPending}
                  onClick={() => submitDecision("rejected")}
                >
                  <X size={16} />
                  Reject
                </button>
              </div>
            </form>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center p-6">
            <EmptyPanel text="Select a review item to inspect its approval status." />
          </div>
        )}
      </section>
    </div>
  );
}

function ReasoningSection({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <section className="space-y-3" aria-label={title}>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-extrabold text-[#1c1c1a]">{title}</h3>
        <span className="rounded-lg bg-[#f0edea] px-2 py-0.5 text-[11px] font-bold text-[#434654]">{count}</span>
      </div>
      {children}
    </section>
  );
}

function ListBlock({ title, values, tone = "neutral" }: { title: string; values: string[]; tone?: "neutral" | "blue" | "green" | "rose" }) {
  if (values.length === 0) {
    return null;
  }
  return (
    <div className="mt-3">
      <p className="text-xs font-bold uppercase text-[#434654]">{title}</p>
      <ul className="mt-1 space-y-1">
        {values.map((value) => (
          <li key={value} className={`rounded-md px-2 py-1.5 text-xs leading-5 ${listToneClass(tone)}`}>
            {value}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ListLine({ label, values }: { label: string; values: string[] }) {
  if (values.length === 0) {
    return null;
  }
  return (
    <p className="mt-1">
      <span className="font-bold">{label}: </span>
      {values.join("; ")}
    </p>
  );
}

function PackItemButtons({
  packItemIds,
  packItems,
  onOpenPackItem,
}: {
  packItemIds: string[];
  packItems: ResearchPackItem[];
  onOpenPackItem: (packItemId: string) => void;
}) {
  const uniqueIds = [...new Set(packItemIds)];
  if (uniqueIds.length === 0) {
    return null;
  }
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {uniqueIds.map((packItemId) => {
        const item = packItems.find((candidate) => candidate.packItemId === packItemId);
        return (
          <button
            key={packItemId}
            className="inline-flex max-w-full items-center gap-1 rounded-md border border-[#c3c6d6] bg-white px-2 py-1 text-xs font-bold text-[#003d9b] hover:border-[#003d9b]"
            type="button"
            title={item?.citation ?? packItemId}
            onClick={() => onOpenPackItem(packItemId)}
          >
            <ExternalLink size={13} />
            <span className="truncate">{packItemId}</span>
          </button>
        );
      })}
    </div>
  );
}

function StatusPill({ children, tone }: { children: ReactNode; tone: "neutral" | "blue" | "green" | "rose" }) {
  return <span className={`rounded-full px-2 py-1 text-[11px] font-bold ${pillToneClass(tone)}`}>{children}</span>;
}

function pillToneClass(tone: "neutral" | "blue" | "green" | "rose"): string {
  if (tone === "blue") {
    return "bg-[#dae2ff] text-[#003d9b]";
  }
  if (tone === "green") {
    return "bg-[#dcfce7] text-[#166534]";
  }
  if (tone === "rose") {
    return "bg-[#ffe4e6] text-[#9f1239]";
  }
  return "bg-[#f0edea] text-[#434654]";
}

function listToneClass(tone: "neutral" | "blue" | "green" | "rose"): string {
  if (tone === "blue") {
    return "bg-[#eef3ff] text-[#003d9b]";
  }
  if (tone === "green") {
    return "bg-[#ecfdf3] text-[#166534]";
  }
  if (tone === "rose") {
    return "bg-[#fff1f2] text-[#9f1239]";
  }
  return "bg-[#f6f3ef] text-[#1c1c1a]";
}

function TabButton({ active = false, icon, label, onClick }: { active?: boolean; icon: ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      className={`inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-bold transition ${
        active ? "bg-[#dae2ff] text-[#003d9b]" : "text-[#434654] hover:bg-[#f0edea] hover:text-[#003d9b]"
      }`}
      type="button"
      onClick={onClick}
      aria-pressed={active}
    >
      {icon}
      {label}
    </button>
  );
}

function PanelHeader({ title, count }: { title: string; count: number }) {
  return (
    <div className="flex items-center justify-between border-b border-[#c3c6d6] bg-[#fcf9f5] px-3 py-3">
      <h2 className="text-sm font-extrabold text-[#1c1c1a]">{title}</h2>
      <span className="rounded-lg bg-[#f0edea] px-2 py-0.5 text-[11px] font-bold text-[#434654]">{count}</span>
    </div>
  );
}

function EmptyPanel({ text }: { text: string }) {
  return <div className="rounded-lg border border-dashed border-[#c3c6d6] bg-[#fcf9f5] p-3 text-xs leading-5 text-[#434654]">{text}</div>;
}

function SummaryPanel({ title, value, body, onClick }: { title: string; value: number; body: string; onClick: () => void }) {
  return (
    <button className="min-h-20 bg-white p-3 text-left transition hover:bg-[#fcf9f5]" type="button" onClick={onClick}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold uppercase tracking-[0.14em] text-[#434654]">{title}</span>
        <span className="rounded-lg bg-[#f0edea] px-2 py-1 text-xs font-bold text-[#434654]">{value}</span>
      </div>
      <p className="mt-2 line-clamp-2 text-xs text-[#1c1c1a]">{body}</p>
    </button>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[#c3c6d6] bg-white p-2.5">
      <dt className="text-xs text-[#434654]">{label}</dt>
      <dd className="mt-1 font-bold text-[#1c1c1a]">{value}</dd>
    </div>
  );
}
