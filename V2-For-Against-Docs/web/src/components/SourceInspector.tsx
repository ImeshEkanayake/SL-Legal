"use client";

import { ExternalLink, FileText, MessageSquare, Network, Package, ShieldAlert, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import type { CaseDocument, DraftSummary, ResearchPackItem, ReviewItem } from "@/lib/workspace-types";

export type InspectorTab = "docs" | "reviews" | "pack" | "reasoning" | "chat";

type SourceInspectorProps = {
  packItems: ResearchPackItem[];
  documents: CaseDocument[];
  drafts: DraftSummary[];
  reviewItems: ReviewItem[];
  selectedPackItemId: string | null;
  activeTab: InspectorTab;
  onActiveTabChange: (tab: InspectorTab) => void;
  onSelectPackItem: (packItemId: string) => void;
  onSelectDocument: (documentId: string) => void;
};

export function SourceInspector({
  packItems,
  documents,
  drafts,
  reviewItems,
  selectedPackItemId,
  activeTab,
  onActiveTabChange,
  onSelectPackItem,
  onSelectDocument,
}: SourceInspectorProps) {
  const selectedItem = packItems.find((item) => item.packItemId === selectedPackItemId) ?? packItems[0] ?? null;
  const selectedDocument = selectedItem ? (documents.find((document) => document.documentId === selectedItem.documentId) ?? null) : (documents[0] ?? null);

  return (
    <aside className="flex h-full min-h-0 w-72 shrink-0 flex-col border-l border-[#c3c6d6] bg-white" aria-label="Source inspector">
      <nav className="grid h-14 shrink-0 grid-cols-5 border-b border-[#c3c6d6]" aria-label="Source inspector views">
        <InspectorTabButton active={activeTab === "docs"} icon={<FileText size={18} />} label="Docs" onClick={() => onActiveTabChange("docs")} />
        <InspectorTabButton active={activeTab === "reviews"} icon={<ShieldCheck size={18} />} label="Reviews" onClick={() => onActiveTabChange("reviews")} />
        <InspectorTabButton active={activeTab === "pack"} icon={<Package size={18} />} label="Pack" onClick={() => onActiveTabChange("pack")} />
        <InspectorTabButton active={activeTab === "reasoning"} icon={<Network size={18} />} label="Reasoning" onClick={() => onActiveTabChange("reasoning")} />
        <InspectorTabButton active={activeTab === "chat"} icon={<MessageSquare size={18} />} label="Chat" onClick={() => onActiveTabChange("chat")} />
      </nav>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {activeTab === "docs" ? <DocumentsPanel documents={documents} onSelectDocument={onSelectDocument} /> : null}
        {activeTab === "reviews" ? <ReviewsPanel drafts={drafts} reviewItems={reviewItems} /> : null}
        {activeTab === "pack" ? <PackPanel packItems={packItems} selectedPackItemId={selectedItem?.packItemId ?? null} onSelectPackItem={onSelectPackItem} /> : null}
        {activeTab === "reasoning" ? <ReasoningPanel drafts={drafts} /> : null}
        {activeTab === "chat" ? (
          <ChatContextPanel
            selectedItem={selectedItem}
            selectedDocument={selectedDocument}
            onSelectDocument={onSelectDocument}
          />
        ) : null}
      </div>

      {selectedDocument ? (
        <footer className="border-t border-[#c3c6d6] bg-[#f6f3ef] p-3">
          <button
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-[#c3c6d6] bg-white px-3 py-2.5 text-xs font-bold text-[#1c1c1a] transition hover:border-[#003d9b] hover:text-[#003d9b]"
            type="button"
            onClick={() => onSelectDocument(selectedDocument.documentId)}
          >
            <ExternalLink size={16} />
            Open document
          </button>
        </footer>
      ) : null}
    </aside>
  );
}

function ReasoningPanel({ drafts }: { drafts: DraftSummary[] }) {
  const reasoningDrafts = drafts.filter((draft) => draft.reasoningPack);
  return (
    <section className="space-y-3">
      <PanelTitle title="Reasoning packs" count={`${reasoningDrafts.length} packs`} />
      {reasoningDrafts.length === 0 ? (
        <EmptyPanel text="Reasoning packs will appear here after Phase 4 draft generation." />
      ) : (
        <div className="space-y-3">
          {reasoningDrafts.map((draft) => (
            <article key={draft.draftId} className="rounded-lg border border-[#c3c6d6] bg-white p-3 text-xs">
              <p className="font-bold text-[#1c1c1a]">{draft.title}</p>
              <p className="mt-2 text-[#434654]">
                {draft.reasoningPack?.issue_matrix.length ?? 0} issues | {draft.reasoningPack?.missing_evidence_checklist.length ?? 0} missing evidence
              </p>
              <p className="mt-2 line-clamp-3 text-[#1c1c1a]">{draft.reasoningPack?.lawyer_review_pack.one_page_case_summary}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function InspectorTabButton({ active, icon, label, onClick }: { active: boolean; icon: ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      className={`flex items-center justify-center border-b-2 transition ${
        active ? "border-[#003d9b] text-[#003d9b]" : "border-transparent text-[#434654] hover:bg-[#f6f3ef] hover:text-[#003d9b]"
      }`}
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={label}
      title={label}
    >
      {icon}
      <span className="sr-only">{label}</span>
    </button>
  );
}

function DocumentsPanel({ documents, onSelectDocument }: { documents: CaseDocument[]; onSelectDocument: (documentId: string) => void }) {
  return (
    <section className="space-y-3">
      <PanelTitle title="Active documents" count={`${documents.length} files`} />
      {documents.length === 0 ? (
        <EmptyPanel text="Case documents will appear here after retrieval or upload." />
      ) : (
        <div className="space-y-3">
          {documents.map((document) => (
            <button
              key={document.documentId}
              className="group flex w-full items-center gap-2.5 rounded-lg border border-[#c3c6d6] bg-white p-2.5 text-left transition hover:border-[#003d9b] hover:bg-[#fcf9f5]"
              type="button"
              onClick={() => onSelectDocument(document.documentId)}
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#f6f3ef] text-[#003d9b]">
                <FileText size={18} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-xs font-bold text-[#1c1c1a]">{document.title}</span>
                <span className="block truncate text-xs text-[#434654]">
                  {document.caseFileAvailable ? "Case file" : "Source only"} | {document.pageCount} pages
                </span>
              </span>
              <ExternalLink className="shrink-0 text-[#737685] group-hover:text-[#003d9b]" size={16} />
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function ReviewsPanel({ drafts, reviewItems }: { drafts: DraftSummary[]; reviewItems: ReviewItem[] }) {
  return (
    <section className="space-y-4">
      <PanelTitle title="Review queue" count={`${reviewItems.length} items`} />
      {reviewItems.length === 0 ? (
        <EmptyPanel text="Lawyer-review tasks will appear here when draft claims are ready." />
      ) : (
        <div className="space-y-3">
          {reviewItems.map((item) => (
            <article key={item.reviewItemId} className="rounded-lg border border-[#c3c6d6] bg-white p-3 text-xs">
              <div className="flex items-center justify-between gap-3">
                <p className="font-bold text-[#1c1c1a]">{item.itemTitle}</p>
                <span className="rounded-full bg-[#f0edea] px-2 py-1 text-xs text-[#434654]">{item.priority}</span>
              </div>
              <p className="mt-2 text-xs text-[#434654]">
                {item.itemType} | {item.status}
              </p>
            </article>
          ))}
        </div>
      )}

      <PanelTitle title="Drafts" count={`${drafts.length} files`} />
      {drafts.length === 0 ? (
        <EmptyPanel text="Pack-bounded drafts will appear here after generation." />
      ) : (
        <div className="space-y-3">
          {drafts.map((draft) => (
            <article key={draft.draftId} className="rounded-lg border border-[#c3c6d6] bg-white p-3 text-xs">
              <p className="font-bold text-[#1c1c1a]">{draft.title}</p>
              <p className="mt-2 text-xs text-[#434654]">
                {draft.draftType} | {draft.status} | {draft.claimCount} claims
              </p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function PackPanel({
  packItems,
  selectedPackItemId,
  onSelectPackItem,
}: {
  packItems: ResearchPackItem[];
  selectedPackItemId: string | null;
  onSelectPackItem: (packItemId: string) => void;
}) {
  return (
    <section className="space-y-3">
      <PanelTitle title="Research pack" count={`${packItems.length} items`} />
      {packItems.length === 0 ? (
        <EmptyPanel text="Cited pack items will appear here after retrieval." />
      ) : (
        <div className="space-y-3">
          {packItems.map((item) => (
            <button
              key={item.packItemId}
              className={`w-full rounded-lg border p-3 text-left text-xs transition ${
                item.packItemId === selectedPackItemId ? "border-[#003d9b] bg-[#dae2ff]" : "border-[#c3c6d6] bg-white hover:border-[#003d9b] hover:bg-[#fcf9f5]"
              }`}
              type="button"
              onClick={() => onSelectPackItem(item.packItemId)}
            >
              <span className="block truncate font-bold text-[#1c1c1a]">{item.citation}</span>
              <span className="mt-1 block truncate text-xs text-[#434654]">{item.packItemId}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function ChatContextPanel({
  selectedItem,
  selectedDocument,
  onSelectDocument,
}: {
  selectedItem: ResearchPackItem | null;
  selectedDocument: CaseDocument | null;
  onSelectDocument: (documentId: string) => void;
}) {
  return (
    <section className="space-y-4">
      <PanelTitle title="Citation context" count={selectedItem ? "selected" : "empty"} />
      {!selectedItem ? (
        <EmptyPanel text="Citation anchors and pack evidence will appear here after retrieval." />
      ) : (
        <>
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#434654]">Selected authority</p>
            <h3 className="mt-2 text-base font-bold text-[#1c1c1a]">{selectedItem.title}</h3>
            <p className="mt-2 text-xs leading-5 text-[#434654]">{selectedItem.selectionReason}</p>
          </div>
          <dl className="grid grid-cols-2 gap-2 text-xs">
            <Metric label="Authority" value={String(selectedItem.authorityLevel)} />
            <Metric label="Score" value={selectedItem.fusedScore.toFixed(3)} />
          </dl>
          {selectedItem.sourceWarnings.length > 0 ? (
            <div className="rounded-lg border border-[#ffb59b] bg-[#fff8e7] p-3 text-xs text-[#7b2600]">
              <div className="mb-1 flex items-center gap-2 font-bold">
                <ShieldAlert size={15} />
                Source warnings
              </div>
              <ul className="list-disc space-y-1 pl-5">
                {selectedItem.sourceWarnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#434654]">Anchors</p>
            <div className="space-y-2">
              {selectedItem.anchors.length === 0 ? (
                <EmptyPanel text="No page anchor has been returned for this pack item." />
              ) : (
                selectedItem.anchors.map((anchor) => (
                  <button
                    key={anchor.anchorId}
                    className="w-full rounded-lg border border-[#c3c6d6] bg-white p-3 text-left text-xs transition hover:border-[#003d9b] hover:bg-[#fcf9f5]"
                    type="button"
                    onClick={() => selectedDocument && onSelectDocument(selectedDocument.documentId)}
                  >
                    <span className="block text-xs font-medium text-[#434654]">Page {anchor.pageNumber ?? "unknown"} | Confidence {Math.round(anchor.confidence * 100)}%</span>
                    <span className="mt-1 block text-[#1c1c1a]">{anchor.quote}</span>
                  </button>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function PanelTitle({ title, count }: { title: string; count: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-[#1c1c1a]">{title}</h2>
      <span className="text-xs font-bold text-[#003d9b]">{count}</span>
    </div>
  );
}

function EmptyPanel({ text }: { text: string }) {
  return <div className="rounded-lg border border-dashed border-[#c3c6d6] bg-[#fcf9f5] p-3 text-xs leading-5 text-[#434654]">{text}</div>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[#c3c6d6] bg-white p-2.5">
      <dt className="text-xs text-[#434654]">{label}</dt>
      <dd className="mt-1 font-bold text-[#1c1c1a]">{value}</dd>
    </div>
  );
}
