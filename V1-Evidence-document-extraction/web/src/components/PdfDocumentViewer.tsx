"use client";

import { ChevronLeft, ChevronRight, Loader2, RotateCw, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from "pdfjs-dist";

type PdfDocumentViewerProps = {
  fileUrl: string;
  title: string;
  fallback: ReactNode;
};

type ViewerState = {
  pageCount: number;
  pageNumber: number;
  scale: number;
  renderVersion: number;
  status: "loading" | "rendering" | "ready" | "error";
  error: string | null;
};

const MIN_SCALE = 0.7;
const MAX_SCALE = 2.2;
const SCALE_STEP = 0.15;

export function PdfDocumentViewer({ fileUrl, title, fallback }: PdfDocumentViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const documentRef = useRef<PDFDocumentProxy | null>(null);
  const [state, setState] = useState<ViewerState>({
    pageCount: 0,
    pageNumber: 1,
    scale: 1.15,
    renderVersion: 0,
    status: "loading",
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    let loadingTask: PDFDocumentLoadingTask | null = null;

    async function loadDocument() {
      setState((current) => ({ ...current, pageCount: 0, pageNumber: 1, status: "loading", error: null }));
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = "/api/pdfjs/worker";
        const response = await fetch(fileUrl, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`File request failed with ${response.status}`);
        }
        const fileBytes = new Uint8Array(await response.arrayBuffer());
        loadingTask = pdfjs.getDocument({ data: fileBytes });
        const pdfDocument = await loadingTask.promise;
        if (cancelled) {
          await pdfDocument.destroy();
          return;
        }
        documentRef.current = pdfDocument;
        setState((current) => ({
          ...current,
          pageCount: pdfDocument.numPages,
          pageNumber: 1,
          renderVersion: current.renderVersion + 1,
          status: "rendering",
          error: null,
        }));
      } catch (error) {
        if (!cancelled) {
          documentRef.current = null;
          setState((current) => ({
            ...current,
            status: "error",
            error: error instanceof Error ? error.message : "Unable to render file.",
          }));
        }
      }
    }

    void loadDocument();
    return () => {
      cancelled = true;
      if (loadingTask) {
        void loadingTask.destroy();
      }
      if (documentRef.current) {
        void documentRef.current.destroy();
        documentRef.current = null;
      }
    };
  }, [fileUrl]);

  useEffect(() => {
    let cancelled = false;
    let renderTask: RenderTask | null = null;
    let timeoutHandle: number | null = null;

    async function renderPage() {
      const pdfDocument = documentRef.current;
      const canvas = canvasRef.current;
      if (!pdfDocument || !canvas || state.pageCount < 1) {
        return;
      }
      setState((current) => ({ ...current, status: "rendering" }));
      try {
        const page = await pdfDocument.getPage(state.pageNumber);
        if (cancelled) {
          return;
        }
        const viewport = page.getViewport({ scale: state.scale });
        const context = canvas.getContext("2d");
        if (!context) {
          throw new Error("Canvas rendering is unavailable.");
        }
        const deviceScale = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * deviceScale);
        canvas.height = Math.floor(viewport.height * deviceScale);
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;
        context.setTransform(deviceScale, 0, 0, deviceScale, 0, 0);
        context.clearRect(0, 0, viewport.width, viewport.height);
        renderTask = page.render({ canvas, canvasContext: context, viewport });
        const timeoutPromise = new Promise<never>((_resolve, reject) => {
          timeoutHandle = window.setTimeout(() => reject(new Error("File rendering timed out.")), 10000);
        });
        await Promise.race([renderTask.promise, timeoutPromise]);
        if (timeoutHandle) {
          window.clearTimeout(timeoutHandle);
          timeoutHandle = null;
        }
        if (!cancelled) {
          setState((current) => ({ ...current, status: "ready", error: null }));
        }
      } catch (error) {
        if (!cancelled && !(error instanceof Error && error.name === "RenderingCancelledException")) {
          setState((current) => ({
            ...current,
            status: "error",
            error: error instanceof Error ? error.message : "Unable to render file.",
          }));
        }
      }
    }

    void renderPage();
    return () => {
      cancelled = true;
      if (timeoutHandle) {
        window.clearTimeout(timeoutHandle);
      }
      if (renderTask) {
        renderTask.cancel();
      }
    };
  }, [state.pageCount, state.pageNumber, state.renderVersion, state.scale]);

  const canGoBack = state.pageNumber > 1;
  const canGoForward = state.pageNumber < state.pageCount;
  const canZoomOut = state.scale > MIN_SCALE;
  const canZoomIn = state.scale < MAX_SCALE;

  return (
    <div className="flex h-full min-h-0 flex-col bg-slate-100">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white px-3 py-2">
        <div className="flex items-center gap-1">
          <IconButton
            label="Previous page"
            disabled={!canGoBack}
            onClick={() => setState((current) => ({ ...current, pageNumber: Math.max(1, current.pageNumber - 1) }))}
          >
            <ChevronLeft size={16} />
          </IconButton>
          <span className="min-w-24 text-center text-sm text-slate-700">
            Page {state.pageNumber} of {state.pageCount || 1}
          </span>
          <IconButton
            label="Next page"
            disabled={!canGoForward}
            onClick={() => setState((current) => ({ ...current, pageNumber: Math.min(current.pageCount, current.pageNumber + 1) }))}
          >
            <ChevronRight size={16} />
          </IconButton>
        </div>
        <div className="flex items-center gap-1">
          <IconButton
            label="Zoom out"
            disabled={!canZoomOut}
            onClick={() => setState((current) => ({ ...current, scale: Math.max(MIN_SCALE, current.scale - SCALE_STEP) }))}
          >
            <ZoomOut size={16} />
          </IconButton>
          <span className="min-w-14 text-center text-sm text-slate-700">{Math.round(state.scale * 100)}%</span>
          <IconButton
            label="Zoom in"
            disabled={!canZoomIn}
            onClick={() => setState((current) => ({ ...current, scale: Math.min(MAX_SCALE, current.scale + SCALE_STEP) }))}
          >
            <ZoomIn size={16} />
          </IconButton>
          <IconButton
            label="Reload file"
            onClick={() =>
              setState((current) => ({
                ...current,
                pageNumber: 1,
                renderVersion: current.renderVersion + 1,
                status: documentRef.current ? "rendering" : "loading",
                error: null,
              }))
            }
          >
            <RotateCw size={16} />
          </IconButton>
        </div>
      </div>
      {state.status === "error" ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[minmax(260px,360px)_1fr]">
          <div className="border-b border-slate-200 bg-white p-4 text-sm leading-6 text-slate-700 lg:border-b-0 lg:border-r">
            <p className="font-semibold text-slate-950">Inline file rendering failed.</p>
            <p className="mt-1">{state.error}</p>
            <a className="mt-3 inline-flex rounded-md border border-slate-300 px-3 py-2 font-medium text-slate-800 hover:bg-slate-50" href={fileUrl} target="_blank" rel="noreferrer">
              Open file
            </a>
          </div>
          {fallback}
        </div>
      ) : (
        <div className="relative min-h-0 flex-1 overflow-auto p-6">
          {state.status !== "ready" ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-100/80 text-sm text-slate-700">
              <span className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 shadow-sm">
                <Loader2 className="animate-spin" size={16} />
                Loading file
              </span>
            </div>
          ) : null}
          <canvas ref={canvasRef} className="mx-auto bg-white shadow-sm" aria-label={`${title} PDF page`} />
        </div>
      )}
    </div>
  );
}

function IconButton({ children, disabled = false, label, onClick }: { children: ReactNode; disabled?: boolean; label: string; onClick: () => void }) {
  return (
    <button
      className="inline-flex size-8 items-center justify-center rounded-md text-slate-700 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-950 disabled:cursor-not-allowed disabled:opacity-40"
      type="button"
      disabled={disabled}
      onClick={onClick}
      aria-label={label}
      title={label}
    >
      {children}
    </button>
  );
}
