import { signedWorkspaceFetch } from "@/lib/workspace-api";

type RouteContext = {
  params: Promise<{
    caseId: string;
    documentId: string;
  }>;
};

const FORWARDED_HEADERS = ["cache-control", "content-disposition", "content-length", "content-type", "etag", "last-modified"];

export async function GET(_request: Request, context: RouteContext): Promise<Response> {
  const { caseId, documentId } = await context.params;
  const backendResponse = await signedWorkspaceFetch(
    `/v1/ui/cases/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(documentId)}/file`,
  );
  const headers = new Headers();
  for (const headerName of FORWARDED_HEADERS) {
    const value = backendResponse.headers.get(headerName);
    if (value) {
      headers.set(headerName, value);
    }
  }
  headers.set("X-Content-Type-Options", "nosniff");
  return new Response(backendResponse.body, {
    status: backendResponse.status,
    statusText: backendResponse.statusText,
    headers,
  });
}
