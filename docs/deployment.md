# Deploy RevSignal on Vercel

RevSignal is configured as one Vercel project with two services:

- `frontend` serves the Next.js website and is the public entry point.
- `revsignal-api` runs the FastAPI backend and remains internal.

The root [`vercel.json`](../vercel.json) configures both services. All public
requests route to the frontend. The frontend's `/api/*` route handler forwards
API calls to the internal backend using the `REVSIGNAL_API_URL` service
binding; `/api/health` is forwarded to the backend's `/health` endpoint.

## Deploy

1. Import `Rohithan-01/revsignal-ai` into Vercel.
2. Set the project root directory to the repository root, not `frontend`.
   Vercel reads the root `vercel.json` to build both services.
3. Deploy the `main` branch. Do not set `REVSIGNAL_API_URL` yourself; Vercel
   injects it from the frontend service binding.
4. Open the deployment URL and check that the dashboard loads. The frontend
   uses labelled demo data if the API cannot be reached.

For local development, run the FastAPI backend on port 8000, then start the
frontend from `frontend` with `npm run dev`. The frontend defaults to
`http://localhost:8000` in development. The Vercel service binding is only
available at runtime in deployed frontend functions.

## Database persistence

The backend defaults to SQLite. A serverless deployment's local filesystem is
not a durable database, so uploaded CRM data may not persist across deployments
or runtime instances. Configure a managed database and set `DATABASE_URL` on
the `revsignal-api` service before relying on persistent data.

## Separate Render deployment

The repository also includes `render.yaml` for deploying the API separately
to Render. That is an alternative to the internal Vercel API service; it is
not required for the Vercel multi-service deployment.
