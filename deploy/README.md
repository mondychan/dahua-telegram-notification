# Production deployment

Copy `.env.example` to `.env` on the Docker host and fill secrets. Login to GHCR with a read-only package token, then run `./deploy/deploy.sh`. The script pulls the GHCR image, starts the service, and waits for its healthcheck.
