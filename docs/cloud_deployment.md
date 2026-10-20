# Cloud Deployment and Hosting Guide

The Cloud Command Broker (`cloud/app.py`) is a standard ASGI FastAPI service that supports async REST webhooks and persistent WebSockets.

---

## 1. Hosting Architecture Comparison and Recurring Costs

Amazon Alexa requires a publicly reachable **HTTPS** endpoint with a valid SSL certificate from a trusted Certificate Authority.

| Provider / Method | Pricing Tier | WebSocket Support | Monthly Cost | Ideal For |
| :--- | :--- | :--- | :--- | :--- |
| **Cloudflare Tunnel (`cloudflared`)** | Free | Yes (Native WSS) | **$0.00 / month** | Running the broker locally or on a home server with zero port forwarding |
| **Render.com** | Hobby / Free Tier | Yes (Native WSS) | **$0.00 - $7.00 / mo** | Easiest cloud deployment via Git repository |
| **Railway.app** | Hobby Tier ($5 credit) | Yes (Native WSS) | **~$3.00 - $5.00 / mo** | Fast single-click Docker container deployment |
| **Fly.io** | Hobby Tier | Yes (Native WSS) | **$0.00 - $3.00 / mo** | Global edge container hosting |
| **AWS Lightsail** | 512MB RAM / 1 vCPU | Yes (Native WSS) | **$3.50 / month** | Fully dedicated Linux VPS with static IPv4 |

*Sources: Render Pricing (render.com/pricing), Railway Pricing (railway.app/pricing), AWS Lightsail Pricing (aws.amazon.com/lightsail/pricing), Cloudflare Zero Trust (cloudflare.com/products/tunnel).*

---

## 2. Option A: Zero-Cost Local Hosting with Cloudflare Tunnel (Recommended for Testing)

If you do not want to deploy to a third-party cloud provider, you can run the broker on your Windows PC and expose it securely via **Cloudflare Tunnel**:
1. Download `cloudflared` from [Cloudflare](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).
2. Run your local broker:
   ```powershell
   .venv\Scripts\python.exe -m uvicorn cloud.app:app --port 8000
   ```
3. In another terminal, run:
   ```powershell
   cloudflared tunnel --url http://localhost:8000
   ```
4. Cloudflare outputs a free public HTTPS address (e.g. `https://random-words.trycloudflare.com`).
5. Enter this URL in the Alexa Developer Console: `https://random-words.trycloudflare.com/alexa`.
6. Set `BROKER_API_URL` and `BROKER_WS_URL` in your `.env`.

---

## 3. Option B: Deployment to Render.com

Render natively supports WebSockets and custom domains:

1. Push this repository to GitHub or GitLab.
2. Sign in to [Render.com](https://render.com/) and click **New +** > **Web Service**.
3. Select your repository.
4. Configure service settings:
   * **Name**: `alexa-windows-broker`
   * **Environment**: `Python 3`
   * **Build Command**: `pip install -r requirements.txt`
   * **Start Command**: `uvicorn cloud.app:app --host 0.0.0.0 --port $PORT`
   * **Instance Type**: `Free` or `Starter` ($7/mo keeps the service continuously awake).
5. In the **Environment Variables** section, add:
   * `AGENT_AUTH_TOKEN`: *(your secure 32+ char token)*
   * `ALEXA_SKILL_ID`: `amzn1.ask.skill.xxxxxxxx`
   * `ALEXA_VERIFY_SIGNATURE`: `true`
   * `DASHBOARD_USERNAME`: `admin`
   * `DASHBOARD_PASSWORD`: *(your secure dashboard password)*
6. Click **Deploy Web Service**.
7. Once deployed, copy your Render URL (e.g. `https://alexa-windows-broker.onrender.com`).
8. In the Alexa Developer Console, enter: `https://alexa-windows-broker.onrender.com/alexa`.

---

## 4. Option C: Deployment with Docker (AWS Lightsail, Railway, DigitalOcean)

The repository includes a ready-to-use `Dockerfile`.

1. Build the Docker container:
   ```bash
   docker build -t alexa-windows-broker .
   ```
2. Run the container:
   ```bash
   docker run -d \
     -p 8000:8000 \
     --name alexa-broker \
     -e AGENT_AUTH_TOKEN="your-secure-token-here" \
     -e ALEXA_VERIFY_SIGNATURE="true" \
     alexa-windows-broker
   ```
3. Use a reverse proxy (Caddy, Nginx, or AWS Application Load Balancer) with a Let's Encrypt SSL certificate for HTTPS termination.
