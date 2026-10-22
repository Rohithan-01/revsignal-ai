# Deploy RevSignal

RevSignal has a FastAPI backend and a separate Next.js frontend. Deploy the
backend to Render and the frontend to Vercel; GitHub stores the source code but
does not run either service.

## Deploy the API to Render

1. Sign in to Render and create a Blueprint from the
   `Rohithan-01/revsignal-ai` GitHub repository.
2. Select the `main` branch and approve the `render.yaml` configuration.
3. After the service deploys, copy its public URL, for example
   `https://revsignal-api.onrender.com`.
4. Open `<API URL>/health`. The response should contain `"status":"ok"`.

The free Render service can spin down while idle. Its SQLite database is not
persistent, so data uploaded to the API can be lost when the service restarts or
is redeployed. Use persistent storage and configure `DATABASE_URL` before
relying on the deployment to retain CRM data.

## Deploy the frontend to Vercel

1. Import the same GitHub repository into Vercel.
2. Set the project **Root Directory** to `frontend`.
3. Add the environment variable
   `NEXT_PUBLIC_API_BASE_URL` with the public Render API URL (without a trailing
   slash), for example `https://revsignal-api.onrender.com`.
4. Deploy and copy the public Vercel site URL.

## Connect the frontend to the API

In the Render service's environment settings, set `CORS_ORIGINS` to include
the exact Vercel site origin, for example:

```text
https://revsignal-ai.vercel.app
```

To allow both the production site and local development, use a comma-separated
list:

```text
https://revsignal-ai.vercel.app,http://localhost:3000,http://127.0.0.1:3000
```

Save the setting and redeploy the Render service. The frontend can then send
API requests to the backend. Vercel preview URLs are separate origins; add a
preview origin to `CORS_ORIGINS` if you need to test a preview deployment.
