
## Configuration

Set the backend URL in [environment.ts](./src/environments/environment.ts) for production builds.
Local development uses [environment.development.ts](./src/environments/environment.development.ts)
automatically.

## Backblaze B2 direct uploads

When `STORAGE_PROVIDER=b2`, files are uploaded directly from the browser to B2
using multipart upload. Configure the B2 bucket CORS rules to allow the
frontend origin for `PUT` and expose the `ETag` response header. For local
development, the rule must allow `http://localhost:4200`; use the deployed
frontend origin in production. Without this rule, the browser will block
multipart part completion even though the signed URLs are valid.

## Database migration and abandoned uploads

After updating the backend, apply the new upload-session migration:

```bash
cd ../backend
alembic upgrade head
```

A direct upload session expires after two hours. Run a dry-run cleanup first:

```bash
python scripts/cleanup_upload_sessions.py
```

To abort expired B2 multipart uploads, use the explicit confirmation:

```bash
python scripts/cleanup_upload_sessions.py \
  --apply \
  --confirm EXPIRE-UPLOADS
```

Schedule that command with the server's task scheduler or cron.

## Development server

To start a local development server, run:

```bash
ng serve
```

Once the server is running, open your browser and navigate to `http://localhost:4200/`. The application will automatically reload whenever you modify any of the source files.

## Code scaffolding

Angular CLI includes powerful code scaffolding tools. To generate a new component, run:

```bash
ng generate component component-name
```

For a complete list of available schematics (such as `components`, `directives`, or `pipes`), run:

```bash
ng generate --help
```

## Building

To build the project run:

```bash
ng build
```

This will compile your project and store the build artifacts in the `dist/` directory. By default, the production build optimizes your application for performance and speed.

## Running unit tests

To execute unit tests with the [Vitest](https://vitest.dev/) test runner, use the following command:

```bash
ng test
```

## Running end-to-end tests

For end-to-end (e2e) testing, run:

```bash
ng e2e
```

Angular CLI does not come with an end-to-end testing framework by default. You can choose one that suits your needs.

## Additional Resources

For more information on using the Angular CLI, including detailed command references, visit the [Angular CLI Overview and Command Reference](https://angular.dev/tools/cli) page.
