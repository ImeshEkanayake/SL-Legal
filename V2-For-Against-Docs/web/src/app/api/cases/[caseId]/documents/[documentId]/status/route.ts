import { signedWorkspaceFetch } from "@/lib/workspace-api";

type RouteContext = {
  params: Promise<{
    caseId: string;
    documentId: string;
  }>;
};

export async function GET(_request: Request, context: RouteContext): Promise<Response> {
  const { caseId, documentId } = await context.params;
  const backendResponse = await signedWorkspaceFetch(
    `/v1/ui/cases/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(documentId)}/status`,
  );
  const headers = new Headers();
  const contentType = backendResponse.headers.get("content-type");
  headers.set("Content-Type", contentType || "application/json");
  headers.set("Cache-Control", "no-store");
  return new Response(await backendResponse.text(), {
    status: backendResponse.status,
    statusText: backendResponse.statusText,
    headers,
  });
}
