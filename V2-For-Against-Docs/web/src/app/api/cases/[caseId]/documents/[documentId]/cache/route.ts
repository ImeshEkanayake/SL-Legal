import { signedWorkspaceFetch } from "@/lib/workspace-api";

type RouteContext = {
  params: Promise<{
    caseId: string;
    documentId: string;
  }>;
};

export async function POST(_request: Request, context: RouteContext): Promise<Response> {
  const { caseId, documentId } = await context.params;
  const backendResponse = await signedWorkspaceFetch(
    `/v1/ui/cases/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(documentId)}/cache`,
    { method: "POST", json: {} },
  );
  const headers = new Headers();
  const contentType = backendResponse.headers.get("content-type");
  headers.set("Content-Type", contentType || "application/json");
  return new Response(await backendResponse.text(), {
    status: backendResponse.status,
    statusText: backendResponse.statusText,
    headers,
  });
}
