# Background Removal API

Self-hosted background removal API, billed per call via API keys with a
credits balance (funded by subscription or one-off top-up in Stripe, wired
up separately). Runs on a Raspberry Pi 5, exposed via Cloudflare Tunnel.

## Local setup

Two ways to run it locally: a plain venv for fast iteration while coding,
or Docker if you want the same environment you'll deploy to the Pi.

**Venv (fast iteration):**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: set API_MASTER_KEY to a long random secret
uvicorn app.main:app --reload
```

**Docker (matches production):**

```bash
cp .env.example .env
# edit .env: set API_MASTER_KEY to a long random secret
docker compose up -d --build
```

First request will be slow while it downloads the ONNX model into the
`model-cache` volume (or `~/.rembg` for the venv path); later restarts are
fast since the model persists.

## Creating an API key

```bash
python manage.py create-key --name "test customer" --credits 20
# or, if running via Docker:
docker compose exec api python manage.py create-key --name "test customer" --credits 20
```

This prints the key once. Give it to the customer, they send it as
`Authorization: Bearer <key>`.

## Using the API

```bash
curl -X POST http://localhost:8000/v1/remove-background \
  -H "Authorization: Bearer <key>" \
  -F "file=@input.jpg" \
  -o output.png
```

Or with a URL instead of a file:

```bash
curl -X POST http://localhost:8000/v1/remove-background \
  -H "Authorization: Bearer <key>" \
  -F "image_url=https://example.com/photo.jpg" \
  -o output.png
```

Check remaining credits:

```bash
curl http://localhost:8000/v1/credits -H "Authorization: Bearer <key>"
```

Interactive API docs: `http://localhost:8000/docs`.

## Admin (key management over HTTP)

Protected by `X-Master-Key` header (the `API_MASTER_KEY` from `.env`).

```bash
curl -X POST http://localhost:8000/admin/keys \
  -H "X-Master-Key: <master key>" \
  -H "Content-Type: application/json" \
  -d '{"name": "test customer", "initial_credits": 20}'
```

Use this endpoint from a Stripe webhook handler later to grant credits on
successful payment (`/admin/keys/{key}/credits`).

## Deploying to the Raspberry Pi

Requires 64-bit Raspberry Pi OS (Bookworm) — `onnxruntime` has no wheel for
the 32-bit armv7l OS. Check with `uname -m`, it must print `aarch64`.

### 1. Copy the code onto the Pi

From your Mac, with the Pi on the same network (replace the hostname if
`raspberrypi.local` doesn't resolve — check your router's client list):

```bash
rsync -avz --exclude venv --exclude data.db --exclude .env \
  /Users/arlind/Developer/bg-removal-api/ pi@raspberrypi.local:/home/pi/bg-removal-api/
```

### 2. Set it up on the Pi

If Docker isn't installed yet (same install path as your trading bot):

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# log out and back in (or `newgrp docker`) for the group change to take effect
```

SSH in (`ssh pi@raspberrypi.local`), then:

```bash
cd /home/pi/bg-removal-api
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # generate a NEW master key for prod
nano .env   # paste the new key into API_MASTER_KEY
docker compose up -d --build
docker compose logs -f   # watch it come up, Ctrl+C to stop watching (container keeps running)
```

Create a real API key to test with:

```bash
docker compose exec api python manage.py create-key --name "my-first-test" --credits 20
```

Smoke-test it locally on the Pi:

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/v1/remove-background \
  -H "Authorization: Bearer <key from above>" -F "file=@some-photo.jpg" -o out.png
```

`restart: unless-stopped` in `docker-compose.yml` means it comes back up
automatically after a reboot or crash, as long as the Docker daemon itself
starts on boot (it does by default once installed via get.docker.com).

### 3. Expose it publicly

**Fastest way to just test from outside your network right now** — a
Cloudflare quick tunnel, no account or domain needed, gives you a random
`*.trycloudflare.com` URL:

```bash
curl -L --output cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64
chmod +x cloudflared && sudo mv cloudflared /usr/local/bin/
cloudflared tunnel --url http://localhost:8000
```

It prints a public HTTPS URL in the terminal — use that as the base URL
from any machine to hit `/health` or `/v1/remove-background`. This tunnel
dies when you Ctrl+C it; fine for a first live test, not for production.

**For a permanent setup** once you have a domain in Cloudflare:

```bash
cloudflared tunnel login
cloudflared tunnel create bg-removal-api
cloudflared tunnel route dns bg-removal-api api.yourdomain.com
```

Copy `deploy/cloudflared-config.example.yml` to `/etc/cloudflared/config.yml`,
fill in the tunnel ID it printed and your hostname, then:

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

Now `https://api.yourdomain.com` is your stable public API URL, backed by
the Pi, without any port forwarding on your router.

## Known limits of this v1

- Concurrency is capped at `MAX_CONCURRENT_JOBS` (default 3) to match the
  Pi 5's 4 cores; requests beyond that queue on the open connection.
- No persistent image storage: images are processed in memory and never
  written to disk, which also keeps this simple from a data-protection
  standpoint.
- Stripe is not wired in yet, only the credits ledger and admin endpoints
  it would call.
- Running a paid service to EU customers will need an Impressum and
  privacy policy before going live, independent of this codebase.
