# Render deployment

The repository includes a Render Blueprint at `../render.yaml` for the FastAPI
service. It uses Render's Free plan; free services can sleep when idle and have
cold starts.

## Deploy the backend

1. Push this repository to GitHub and create a Blueprint in Render from it.
2. Set the Blueprint's required environment variables in Render:
   - `DATABASE_URL`: Supabase Postgres connection string using the
     `postgresql+psycopg://` SQLAlchemy scheme. Use the direct connection or an
     appropriate session pooler URL.
   - `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`: the server-side Supabase
     project URL and service-role key. Never expose the service-role key in the
     frontend or commit it to the repository.
   - `SECRET_KEY`: a long, random signing key, kept only in Render's environment.
   - `FRONTEND_ORIGIN`: the deployed Vercel origin, with no trailing slash.
3. Before deploying a release that adds or changes a migration, apply all
   pending schema migrations against the target database:

   ```sh
   cd backend
   alembic upgrade head
   ```

   Run this from an environment with the deployment `DATABASE_URL` set. Do not
   put the database URL in source control or share it in chat.
4. Confirm Render's `/health` endpoint responds with `{"status":"ok"}`.

The service defaults to Supabase Storage. If you configure Backblaze B2 instead,
set `STORAGE_PROVIDER=b2` and provide `B2_ENDPOINT`, `B2_BUCKET`, `B2_KEY_ID`,
and `B2_APPLICATION_KEY` as Render environment variables.

## Connect the frontend

After Render gives the API its public URL, set
`frontend/src/environments/environment.ts`'s `apiUrl` to that URL and redeploy
the frontend to Vercel. If the Vercel origin changes, update `FRONTEND_ORIGIN`
in Render and restart/redeploy the API.

## Upload behavior

Uploads accept any file extension. The file is stored as an attachment, with
preview limited to supported safe formats. The current maximum file size is
500 MB, subject to the user's available storage quota. A macOS `.app` is a
package directory rather than a single file; compress it to an archive before
uploading the complete app.

Render Free services sleep after inactivity. Verify large-file uploads against
the deployed service; long-running requests may be affected by the host's
request limits.
