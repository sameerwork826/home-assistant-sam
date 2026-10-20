# Custom Alexa-to-Windows Command Execution System (TriggerCMD Alternative)

A complete, private, self-hosted system that allows you to control your Windows 11 laptop using voice commands through an Amazon Alexa smart speaker.

Includes a **modern Windows 11 Desktop GUI** with a **TriggerCMD-style command manager** where you can enter any command or script you want executed on your computer and trigger it by voice.

---

## 1. What Makes This Better Than TriggerCMD & IFTTT?

| Feature | TriggerCMD | Our System |
| :--- | :--- | :--- |
| **Command Frequency Limit** | **Arbitrary 1 trigger per minute limit** | **Zero artificial cooldowns** (run multiple commands in seconds) |
| **Third-Party Dependency** | Proprietary cloud + paid subscriptions | **100% Self-Hosted & Private** |
| **Custom Command Creation** | Web dashboard with cooldowns | **Instant Desktop GUI & `custom_commands.json`** |
| **Security Architecture** | Often runs arbitrary unverified scripts | **Predefined & User-Allowed Commands with Confirmation** |
| **Alexa Voice Feedback** | Generic "Trigger sent" | **Honest real-time spoken outcome & error reporting** |
| **Destructive Safeguards** | Ambiguous immediate execution | **Mandatory Two-Step Confirmation** for Shutdown & Restart |
| **Firewall / Router** | Proprietary agent | **Outbound TLS Persistent WebSocket** (no open router ports) |
| **Session Isolation** | Can run invisibly in Session 0 | **Interactive Session 1+ Launcher** (GUI apps open visibly) |

---

## 2. Windows Agent Desktop GUI

The Windows Agent includes a modern dark-mode desktop interface built with CustomTkinter.

```
+---------------------------------------------------------------------------------------+
|  Alexa PC Command Agent                                      [ ● CONNECTED ]          |
|  Broker: wss://my-broker.onrender.com/ws/agent  |  Windows: Session 1 (Interactive)   |
|  Uptime: 4h 12m 30s                                                                   |
+---------------------------------------------------------------------------------------+
|  [ Custom & Predefined Commands ]   [ Live Execution Logs ]   [ Agent Settings ]      |
+---------------------------------------------------------------------------------------+
|                                                                                       |
|  USER CUSTOM COMMANDS (TRIGGERCMD STYLE)                         [ + Add Command ]    |
|                                                                                       |
|  +---------------------------------------------------------------------------------+  |
|  | Trigger: "notepad"        [CUSTOM]                               [ Run ] [ Edit ] |  |
|  | Runs: notepad.exe • Launches Windows Notepad                     [ Delete ]        |  |
|  +---------------------------------------------------------------------------------+  |
|  | Trigger: "calculator"     [CUSTOM]                               [ Run ] [ Edit ] |  |
|  | Runs: calc.exe • Launches Windows Calculator                     [ Delete ]        |  |
|  +---------------------------------------------------------------------------------+  |
|  | Trigger: "steam"          [CUSTOM]                               [ Run ] [ Edit ] |  |
|  | Runs: "C:\Program Files (x86)\Steam\steam.exe"                  [ Run ] [ Edit ] |  |
|  +---------------------------------------------------------------------------------+  |
|                                                                                       |
|  BUILT-IN SYSTEM COMMANDS                                                             |
|                                                                                       |
|  +---------------------------------------------------------------------------------+  |
|  | Trigger: "lock_pc"        [BUILT-IN]                                     [ Run ]  |  |
|  | Runs: user32.dll LockWorkStation • Locks the workstation screen                    |  |
|  +---------------------------------------------------------------------------------+  |
|  | Trigger: "shutdown_pc"    [BUILT-IN]  [CONFIRMATION REQUIRED]            [ Run ]  |  |
|  | Runs: shutdown.exe /s /t 60 • Initiates scheduled Windows shutdown                |  |
|  +---------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------+
```

### GUI Features:
1. **Live Connection Pill**: Displays real-time WebSocket connection state (`CONNECTED` in green, `CONNECTING` in yellow, `OFFLINE` in red).
2. **Session Verification**: Displays your active Windows Session ID (Session 1+ verified for interactive GUI applications).
3. **TriggerCMD Command Manager**:
   - Click **"+ Add Command"** to define any new command.
   - Built-in **File Browser (`Browse...`)** to pick any `.exe`, `.bat`, `.cmd`, or `.ps1` file.
   - Click **"Run"** next to any command to test it locally right from the GUI.
   - Edit or delete custom commands on the fly.
4. **Live Execution Log**: Displays real-time voice invocations, timestamps, execution latency in milliseconds, and error messages.
5. **Double-Click Launch**: Launch directly by double-clicking `scripts\start_gui.bat`.

---

## 3. How Custom Commands Work (TriggerCMD Style)

Just like TriggerCMD, you don't need to write code to add new voice triggers. You simply specify **what command line to execute** on your Windows laptop!

### Creating a Custom Command in 30 Seconds:
1. Open the Agent GUI (or run `.venv\Scripts\python.exe -m windows_agent.main --gui`).
2. Click the blue **"+ Add Command"** button.
3. Fill in the fields:
   * **Trigger Name**: The voice trigger word (e.g. `notepad`, `calculator`, `steam`, `spotify`, `backup`, `vlc`).
   * **Command Line to Execute**: The exact command or script to run:
     - `notepad.exe`
     - `calc.exe`
     - `C:\Users\nande\scripts\backup.bat`
     - `powershell.exe -ExecutionPolicy Bypass -File C:\scripts\mute.ps1`
     - `"C:\Program Files\VideoLAN\VLC\vlc.exe" "C:\media\music.mp3"`
   * **Description**: A friendly note describing the action.
   * **Voice Confirmation Switch**: Turn this ON for risky actions (Alexa will ask: *"Are you sure? Say yes to confirm"*).
4. Click **Save Command**.

### Triggering via Voice with Alexa:
Once saved, you can immediately say to any Amazon Echo or Alexa device:
* *"Alexa, ask My PC to run Notepad"*
* *"Alexa, ask My PC to run Calculator"*
* *"Alexa, ask My PC to run Steam"*
* *"Alexa, ask My PC to trigger {YourTriggerName}"*
* *"Alexa, ask My PC to start {YourTriggerName}"*

The command executes instantly on your Windows laptop desktop!

### Under the Hood (`custom_commands.json`):
Custom commands are persisted to `custom_commands.json` in your project folder:
```json
[
  {
    "trigger_name": "notepad",
    "command_line": "notepad.exe",
    "description": "Launches Windows Notepad",
    "confirmation_required": false,
    "enabled": true
  },
  {
    "trigger_name": "calculator",
    "command_line": "calc.exe",
    "description": "Launches Windows Calculator",
    "confirmation_required": false,
    "enabled": true
  }
]
```
You can edit this file directly or manage it completely through the GUI.

---

## 4. Built-in Predefined Voice Commands

In addition to custom commands, the system includes 10 hardened core operating system commands:

| Command ID | Voice Utterance Example | Risk Level | Confirmation | Action |
| :--- | :--- | :---: | :---: | :--- |
| `open_chrome` | *"Alexa, ask My PC to open Chrome"* | Low | No | Launches Google Chrome |
| `open_vscode` | *"Alexa, ask My PC to open VS Code"* | Low | No | Launches Visual Studio Code |
| `open_website` | *"Alexa, ask My PC to open YouTube"* | Low | No | Opens allowlisted URL in browser |
| `lock_pc` | *"Alexa, ask My PC to lock the computer"* | Low | No | Locks Windows workstation |
| `shutdown_pc` | *"Alexa, ask My PC to shut down my computer"* | High | **Yes** | 60s delayed shutdown (with abort) |
| `restart_pc` | *"Alexa, ask My PC to restart my computer"* | High | **Yes** | 60s delayed restart (with abort) |
| `sleep_pc` | *"Alexa, ask My PC to put the computer to sleep"* | Medium | No | Suspends Windows workstation |
| `cancel_shutdown` | *"Alexa, ask My PC to cancel shutdown"* | Low | No | Cancels scheduled shutdown |
| `pc_status` | *"Alexa, ask My PC for its status"* | Low | No | Reports uptime, lock state, session |
| `command_status` | *"Alexa, ask My PC did the last command work"* | Low | No | Reports last execution outcome |

---

## 5. System Architecture

```
 [ Alexa Smart Speaker / Echo ]
               |
               v (Spoken: "Alexa, ask My PC to run Notepad")
 [ Amazon Alexa Voice Service ]
               |
               v (HTTPS POST with RSA-SHA256 Amazon Signature Verification)
 [ Cloud Command Broker (FastAPI) ]
               |
               v (Outbound TLS Persistent WebSocket wss:// + Heartbeat Keep-Alive)
 [ Windows Command Agent & GUI ] (Runs in Interactive Desktop Session 1+)
               |
               +--> Custom Commands Manager (custom_commands.json)
               +--> Predefined Allowlist Registry
               v
 [ Windows 11 Operating System & Applications ]
 (Notepad, Calculator, Chrome, VS Code, Custom Scripts)
```

* **No Router Port Forwarding**: The Windows agent initiates an outbound connection over TLS to the cloud broker.
* **Sub-Second Execution**: Persistent WebSockets enable sub-50ms command delivery. Alexa verifies execution and speaks the real outcome before the speech deadline.
* **No Session 0 Black Hole**: The agent runs in your logged-in interactive desktop session, ensuring applications launch visibly on your desktop.

---

## 6. Quickstart Installation Guide

### Step 1: Install Python Environment with `uv`

```powershell
# 1. Clone repository and change directory
cd c:\Users\nande\Desktop\projects\home-assistant-sam

# 2. Create virtual environment with uv
uv venv .venv

# 3. Install all dependencies (FastAPI, WebSockets, CustomTkinter, Cryptography)
uv pip install -e .[dev]

# 4. Copy configuration template
Copy-Item .env.example .env
```

### Step 2: Configure `.env`
Edit `.env` and set:
```ini
AGENT_AUTH_TOKEN=your-random-32-character-secret-token
ALEXA_SKILL_ID=amzn1.ask.skill.your-skill-id-here
ALEXA_VERIFY_SIGNATURE=true
```

### Step 3: Run the Automated Tests (48 Tests)
```powershell
.venv\Scripts\pytest.exe -v
```
All 48 unit, custom command, and integration tests pass in ~0.6 seconds!

### Step 4: Launch the Windows Agent GUI
You can start the modern desktop GUI in any of these ways:
* **Option A**: Double-click `scripts\start_gui.bat` in File Explorer.
* **Option B**: Run from PowerShell:
  ```powershell
  .venv\Scripts\python.exe -m windows_agent.main --gui
  ```

---

## 7. Cloud Deployment Options

### Option A: Free Local Testing with Cloudflare Tunnel (Zero Cost)
1. Start the broker locally:
   ```powershell
   .venv\Scripts\python.exe -m uvicorn cloud.app:app --port 8000
   ```
2. In another terminal, run:
   ```powershell
   cloudflared tunnel --url http://localhost:8000
   ```
3. Cloudflare outputs a free public HTTPS URL (e.g. `https://example.trycloudflare.com`).
4. Set your Alexa Skill endpoint to: `https://example.trycloudflare.com/alexa`.

### Option B: Cloud Deployment on Render.com (or Railway / Docker)
1. Push this repository to GitHub.
2. In [Render.com](https://render.com), create a **New Web Service**:
   * Build command: `pip install -r requirements.txt`
   * Start command: `uvicorn cloud.app:app --host 0.0.0.0 --port $PORT`
   * Environment variables: `AGENT_AUTH_TOKEN`, `ALEXA_SKILL_ID`, `ALEXA_VERIFY_SIGNATURE=true`.
3. Set your Alexa Skill endpoint to: `https://<your-service>.onrender.com/alexa`.

See [docs/cloud_deployment.md](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/cloud_deployment.md) for full instructions and cost comparisons.

---

## 8. Alexa Skill Setup in 3 Minutes

1. Sign in to the [Amazon Alexa Developer Console](https://developer.amazon.com/alexa/console/ask).
2. Click **Create Skill**:
   * **Skill Name**: `My PC Controller`
   * **Invocation Name**: `my pc`
   * **Model**: `Custom`
   * **Hosting**: `Provision your own`
3. Under **Interaction Model** > **JSON Editor**, paste the contents of [alexa_skill/interaction_model/en-US.json](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/alexa_skill/interaction_model/en-US.json), save, and click **Build Model**.
4. Under **Endpoint**, select **HTTPS**, enter your cloud URL (e.g. `https://my-broker.onrender.com/alexa`), and select the wildcard SSL certificate option.
5. In the **Test** tab, change test mode to **Development**.
6. Try speaking or typing:
   * *"ask my pc to open chrome"*
   * *"ask my pc to run notepad"*
   * *"ask my pc to check status"*

See [docs/alexa_setup.md](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/alexa_setup.md) for detailed step-by-step instructions.

---

## 9. Auto-Starting on Windows User Login

To ensure the agent launches silently in your interactive desktop session whenever you sign in:

```powershell
.venv\Scripts\python.exe scripts\install_startup_task.py
```

This installs a silent VBS launcher in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\` that starts the agent in **Session 1+** so GUI applications appear visibly on your desktop.

To uninstall:
```powershell
.venv\Scripts\python.exe scripts\install_startup_task.py uninstall
```

---

## 10. Web Dashboard

Visit `https://<YOUR-BROKER-URL>/dashboard`:
* Live view of connected Windows laptops.
* Active session ID, username, lock state, and system uptime.
* Real-time command execution history, latencies, and error logs.
* Protected by HTTP Basic Authentication.

---

## 11. Documentation Links

* [System Architecture](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/architecture.md): Protocols, session isolation, and concurrency.
* [Security & Hardening](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/security.md): Cryptographic verification, allowlists, and replay defense.
* [Alexa Skill Setup](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/alexa_setup.md): Complete setup walkthrough in the Amazon Developer Console.
* [Cloud Deployment](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/cloud_deployment.md): Render, Docker, Railway, AWS Lightsail, and Cloudflare Tunnel.
* [Windows Agent Setup](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/windows_setup.md): Windows 11 setup, session behavior under sleep/lock, and startup task.
* [Troubleshooting Guide](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/troubleshooting.md): Common error resolutions and diagnostics.
* [Adding New Commands](file:///c:/Users/nande/Desktop/projects/home-assistant-sam/docs/adding_commands.md): Step-by-step tutorial on expanding the command registry.
