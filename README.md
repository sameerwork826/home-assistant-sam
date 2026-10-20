# Custom Alexa-to-Windows Command Execution System

A secure, private, self-hosted alternative to **TriggerCMD** that allows you to control your Windows 11 laptop using voice commands through an Amazon Alexa smart speaker.

---

## 1. Why Build This? (Comparison with TriggerCMD & IFTTT)

| Feature | TriggerCMD | Our Custom System |
| :--- | :--- | :--- |
| **Command Frequency** | **Limited to 1 trigger per minute** | **Zero artificial cooldowns** (rapid succession supported) |
| **Third-Party Dependency** | Proprietary cloud + subscription | **100% Self-Hosted & Private** |
| **Security Architecture** | Often runs arbitrary batch scripts | **Strict Predefined Allowlist & Parameter Sanitization** |
| **Voice Feedback** | Generic "Trigger sent" | **Honest real-time execution outcome in speech** |
| **Destructive Safeguards** | Ambiguous immediate execution | **Mandatory Two-Step Confirmation** for Shutdown & Restart |
| **Connection Mechanism** | Proprietary agent | **Outbound TLS Persistent WebSocket** (no open router ports) |
| **Session Handling** | Can suffer from Session 0 invisibility | **Interactive Session 1+ Launcher** (GUI apps open visibly) |

---

## 2. Implemented Predefined Voice Commands

| Command ID | Voice Utterance Example | Risk Level | Confirmation Required | Execution Mechanism |
| :--- | :--- | :--- | :--- | :--- |
| `open_chrome` | *"Alexa, ask My PC to open Chrome"* | Low | No | Detached process in user session |
| `open_vscode` | *"Alexa, ask My PC to open VS Code"* | Low | No | Detached process in user session |
| `open_website` | *"Alexa, ask My PC to open YouTube"* | Low | No | Allowlisted URL validation & browser launch |
| `lock_pc` | *"Alexa, ask My PC to lock the computer"* | Low | No | `user32.dll LockWorkStation` |
| `shutdown_pc` | *"Alexa, ask My PC to shut down my computer"* | High | **Yes** ("Say yes to confirm") | `shutdown.exe /s /t 60` (with 60s abort buffer) |
| `restart_pc` | *"Alexa, ask My PC to restart my computer"* | High | **Yes** ("Say yes to confirm") | `shutdown.exe /r /t 60` (with 60s abort buffer) |
| `sleep_pc` | *"Alexa, ask My PC to put the computer to sleep"* | Medium | No | `powrprof.dll SetSuspendState` |
| `cancel_shutdown` | *"Alexa, ask My PC to cancel shutdown"* | Low | No | `shutdown.exe /a` |
| `pc_status` | *"Alexa, ask My PC for its status"* | Low | No | Reports uptime, lock state, session ID, user |
| `command_status` | *"Alexa, ask My PC did the last command work"* | Low | No | Reports last command outcome & error |

---

## 3. Architecture Overview

```
 [ Alexa Smart Speaker ]
           |
           v
 [ Amazon Alexa Voice Service ]
           |
           v (HTTPS POST with RSA-SHA256 Amazon Signature)
 [ Cloud Command Broker (FastAPI) ]
           |
           v (Outbound TLS Persistent WebSocket wss:// + Heartbeat)
 [ Windows Command Agent ] (Runs in Interactive Session 1+)
           |
           v (Allowlist Validation & Subprocess shell=False)
 [ Windows 11 Operating System & Applications ]
```

* **No Router Port Forwarding**: The Windows agent initiates an outbound connection over TLS to the cloud broker.
* **Sub-Second Latency**: Persistent WebSockets enable Alexa to deliver commands in <50ms and speak the verified result back to you before the speech timeout.
* **No Session 0 Black Hole**: The agent runs in the logged-in interactive desktop session, ensuring Chrome and VS Code open visibly on your screen.

---

## 4. Quickstart Guide

### Step 1: Install Python Environment with `uv`

```powershell
# Clone and enter directory
cd c:\Users\nande\Desktop\projects\home-assistant-sam

# Create virtual environment with uv
uv venv .venv

# Install project dependencies
uv pip install -e .[dev]

# Create local configuration file
Copy-Item .env.example .env
```

### Step 2: Configure `.env`
Edit `.env` and set:
```ini
AGENT_AUTH_TOKEN=your-random-32-character-secret-token
ALEXA_SKILL_ID=amzn1.ask.skill.your-skill-id-here
ALEXA_VERIFY_SIGNATURE=true
```

### Step 3: Run the Automated Tests (40 Tests)
```powershell
.venv\Scripts\pytest.exe -v
```
All 40 unit and end-to-end integration tests pass in ~0.6 seconds!

### Step 4: Test Local Command Execution
```powershell
# Inspect session, uptime, and user
.venv\Scripts\python.exe -m windows_agent.main --status

# Test launching Chrome locally
.venv\Scripts\python.exe -m windows_agent.main --test-command open_chrome

# Test opening an approved website
.venv\Scripts\python.exe -m windows_agent.main --test-command open_website --param website_name=google
```

---

## 5. Deployment Options

### Option A: Zero-Cost Cloudflare Tunnel (Recommended for Immediate Local Testing)
1. Start the Cloud Broker locally:
   ```powershell
   .venv\Scripts\python.exe -m uvicorn cloud.app:app --port 8000
   ```
2. In a second terminal, launch a Cloudflare Tunnel:
   ```powershell
   cloudflared tunnel --url http://localhost:8000
   ```
3. Cloudflare gives you a free public HTTPS address with a trusted wildcard SSL certificate.
4. Set this URL as your Alexa endpoint: `https://<tunnel-subdomain>.trycloudflare.com/alexa`.

### Option B: Deploy to Render.com (or Railway / Fly.io)
1. Push this repository to GitHub.
2. Create a new Web Service on [Render.com](https://render.com/).
3. Start command: `uvicorn cloud.app:app --host 0.0.0.0 --port $PORT`.
4. Add environment variables: `AGENT_AUTH_TOKEN`, `ALEXA_SKILL_ID`, `ALEXA_VERIFY_SIGNATURE=true`.
5. Enter your Render URL into the Alexa Developer Console: `https://<service-name>.onrender.com/alexa`.

See [docs/cloud_deployment.md](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/cloud_deployment.md) for full instructions and recurring cost breakdowns.

---

## 6. Configuring the Alexa Skill

1. Sign in to the [Amazon Alexa Developer Console](https://developer.amazon.com/alexa/console/ask).
2. Click **Create Skill**:
   * Name: `My PC Controller`
   * Model: `Custom`
   * Hosting: `Provision your own`
3. Set **Skill Invocation Name** to `my pc`.
4. Go to **Interaction Model** > **JSON Editor**, paste the contents of `alexa_skill/interaction_model/en-US.json`, save, and click **Build Model**.
5. Go to **Endpoint**, select **HTTPS**, enter `https://<YOUR-DOMAIN>/alexa`, and select the wildcard SSL certificate option.
6. Test in the **Test** tab by typing: `ask my pc to open chrome`.

See [docs/alexa_setup.md](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/alexa_setup.md) for detailed step-by-step screenshots and guidelines.

---

## 7. Installing the Windows Agent as a Startup Task

To automatically start the agent when you log into Windows:

```powershell
.venv\Scripts\python.exe scripts\install_startup_task.py
```

This creates a silent VBS launcher in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\` that runs the agent in the background of your interactive desktop session without leaving a black CMD window open.

To uninstall:
```powershell
.venv\Scripts\python.exe scripts\install_startup_task.py uninstall
```

---

## 8. Web Dashboard

Visit `https://<YOUR-DOMAIN>/dashboard` (or `http://localhost:8000/dashboard` locally):
* Real-time online/offline status of connected Windows agents.
* Active session ID, user, and workstation lock state.
* Live command execution history, latencies, and error logs.
* Protected by HTTP Basic Authentication.

---

## 9. Documentation Index

* [System Architecture](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/architecture.md): Topology, communication protocols, session isolation, and concurrency.
* [Security & Hardening](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/security.md): Cryptographic verification, allowlists, rate limiting, and replay defense.
* [Alexa Skill Setup](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/alexa_setup.md): Complete setup walkthrough in the Amazon Developer Console.
* [Cloud Deployment](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/cloud_deployment.md): Render, Docker, Railway, AWS Lightsail, and Cloudflare Tunnel.
* [Windows Agent Setup](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/windows_setup.md): Windows 11 setup, session behavior under sleep/lock, and startup task.
* [Troubleshooting Guide](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/troubleshooting.md): Common error resolutions and diagnostics.
* [Adding New Commands](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/adding_commands.md): Step-by-step tutorial on expanding the command registry.
