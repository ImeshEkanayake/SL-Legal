"use client";

import { FileText, Folder, MessageSquarePlus, Search, Settings } from "lucide-react";
import { useMemo, useRef } from "react";
import type { WorkspaceCase, WorkspaceProject } from "@/lib/workspace-types";

type ProjectRailProps = {
  projects: WorkspaceProject[];
  cases: WorkspaceCase[];
  activeCaseId: string | null;
  query: string;
  onQueryChange: (query: string) => void;
  onSelectCase: (caseId: string) => void;
  onOpenNewCase: () => void;
  onOpenSettings: () => void;
};

export function ProjectRail({
  projects,
  cases,
  activeCaseId,
  query,
  onQueryChange,
  onSelectCase,
  onOpenNewCase,
  onOpenSettings,
}: ProjectRailProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const normalizedQuery = query.trim().toLowerCase();
  const visibleCases = useMemo(() => {
    if (!normalizedQuery) {
      return cases;
    }
    return cases.filter((caseItem) =>
      [caseItem.title, caseItem.court, caseItem.matterType]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(normalizedQuery),
    );
  }, [cases, normalizedQuery]);

  return (
    <aside className="flex h-full min-h-0 w-full shrink-0 flex-col border-r border-[#c3c6d6] bg-[#fcf9f5] text-[#1c1c1a] md:w-56">
      <div className="px-4 pb-5 pt-5">
        <p className="text-base font-extrabold text-[#003d9b]">LegalMind AI</p>
        <p className="mt-0.5 text-xs text-[#434654]">Precision Research</p>
      </div>
      <div className="flex items-center gap-2 px-3 pb-3">
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-[#434654] transition hover:bg-[#f0edea] hover:text-[#003d9b]"
          aria-label="Focus matter search"
          type="button"
          onClick={() => inputRef.current?.focus()}
        >
          <Search size={18} />
        </button>
        <button
          className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-lg bg-[#003d9b] px-2 text-xs font-bold text-white transition hover:bg-[#0052cc]"
          type="button"
          onClick={onOpenNewCase}
        >
          <MessageSquarePlus size={17} />
          New matter
        </button>
      </div>
      <div className="border-y border-[#c3c6d6] px-3 py-3">
        <label className="sr-only" htmlFor="matter-search">
          Search matters
        </label>
        <input
          ref={inputRef}
          id="matter-search"
          className="h-9 w-full rounded-lg border border-[#c3c6d6] bg-white px-3 text-xs text-[#1c1c1a] outline-none transition placeholder:text-[#737685] focus:border-[#003d9b] focus:ring-2 focus:ring-[#003d9b]/10"
          placeholder="Search matters"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
        />
      </div>
      <nav className="min-h-0 flex-1 overflow-y-auto px-2.5 py-4" aria-label="Projects and cases">
        {projects.length === 0 ? (
          <div className="rounded-lg border border-[#c3c6d6] bg-white p-3 text-xs leading-5 text-[#434654]">
            Create or open a matter to load projects, chats, source documents, and review queues.
          </div>
        ) : (
          projects.map((project) => {
            const projectCases = visibleCases.filter((caseItem) => caseItem.projectId === project.projectId);
            if (projectCases.length === 0 && normalizedQuery) {
              return null;
            }
            return (
              <section key={project.projectId} className="mb-6">
                <div className="mb-2 flex items-center gap-2 px-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-[#434654]">
                  <Folder size={15} />
                  <span className="truncate">{project.name}</span>
                  <span className="ml-auto rounded-lg bg-[#f0edea] px-2 py-1 text-[11px] text-[#434654]">{project.activeCaseCount}</span>
                </div>
                <div className="space-y-1.5">
                  {projectCases.map((caseItem) => {
                    const active = caseItem.caseId === activeCaseId;
                    return (
                      <button
                        key={caseItem.caseId}
                        className={`flex w-full items-start gap-2 rounded-lg px-2.5 py-2.5 text-left text-xs transition ${
                          active ? "border-l-4 border-[#003d9b] bg-[#dae2ff] text-[#003d9b]" : "text-[#434654] hover:bg-[#f6f3ef] hover:text-[#003d9b]"
                        }`}
                        type="button"
                        onClick={() => onSelectCase(caseItem.caseId)}
                      >
                        <FileText className="mt-0.5 shrink-0" size={17} />
                        <span className="min-w-0">
                          <span className="block truncate font-bold">{caseItem.title}</span>
                          <span className={`block truncate text-xs ${active ? "text-[#0040a2]" : "text-[#737685]"}`}>{caseItem.court || caseItem.matterType || "Matter"}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </section>
            );
          })
        )}
        {projects.length > 0 && visibleCases.length === 0 ? (
          <div className="rounded-lg border border-[#c3c6d6] bg-white p-4 text-sm text-[#434654]">
            No matters match the current search.
          </div>
        ) : null}
      </nav>
      <div className="border-t border-[#c3c6d6] p-3">
        <button
          className="inline-flex w-full items-center gap-2 rounded-lg px-2.5 py-2.5 text-xs font-bold text-[#434654] transition hover:bg-[#f6f3ef] hover:text-[#003d9b]"
          type="button"
          onClick={onOpenSettings}
        >
          <Settings size={16} />
          Settings
        </button>
      </div>
    </aside>
  );
}
