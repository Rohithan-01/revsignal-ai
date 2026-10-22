type RouteContext = {
  params: Promise<{ path: string[] }>;
};

async function proxyToApi(request: Request, context: RouteContext): Promise<Response> {
  const apiBaseUrl = process.env.REVSIGNAL_API_URL;
  if (!apiBaseUrl) {
    throw new Error("The REVSIGNAL_API_URL Vercel service binding is not configured.");
  }

  const { path } = await context.params;
  const encodedPath = path.map(encodeURIComponent).join("/");
  const apiPath =
    path.length === 1 && path[0] === "health"
      ? "/health"
      : `/api/${encodedPath}`;
  const targetUrl = new URL(apiPath, apiBaseUrl);
  targetUrl.search = new URL(request.url).search;

  const requestHeaders = new Headers(request.headers);
  for (const header of ["connection", "content-length", "host", "transfer-encoding"]) {
    requestHeaders.delete(header);
  }

  const response = await fetch(targetUrl, {
    method: request.method,
    headers: requestHeaders,
    body:
      request.method === "GET" || request.method === "HEAD"
        ? undefined
        : await request.arrayBuffer(),
    cache: "no-store",
  });

  const responseHeaders = new Headers(response.headers);
  for (const header of [
    "connection",
    "content-encoding",
    "content-length",
    "transfer-encoding",
  ]) {
    responseHeaders.delete(header);
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxyToApi;
export const POST = proxyToApi;
