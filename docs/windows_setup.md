# Windows 11 Agent Setup and Operation Guide

This guide explains how to install, configure, operate, and uninstall the Windows Command Agent on your Windows 11 laptop.

---

## 1. Prerequisites

* **Operating System**: Windows 11 (or Windows 10 64-bit).
* **Python**: Python 3.10+ (managed via `uv` or standard Python installer).
* **PowerShell**: Windows PowerShell 5.1 or PowerShell Core 7+.

---

## 2. Quick Installation with `uv`

If you use `uv` (recommended):

```powershell
# 1. Clone repository and change directory
cd c:\Users\nande\Desktop\projects\home-assistant-sam

# 2. Create the virtual environment using Python 3.13 / 3.12
uv venv .venv

# 3. Install dependencies
uv pip install -e .[dev]

# 4. Copy the environment configuration template
Copy-Item .env.example .env
```

---

## 3. Configuration (.env)

Open `.env` in VS Code or Notepad and customize your settings:

```ini
# Address of your Cloud Command Broker
BROKER_API_URL=https://<YOUR-CLOUD-DOMAIN>
BROKER_WS_URL=wss://<YOUR-CLOUD-DOMAIN>/ws/agent

# Must match AGENT_AUTH_TOKEN configured on the Cloud Broker
AGENT_AUTH_TOKEN=your-random-32-character-secret-token

# Identifier for this machine
AGENT_ID=windows-laptop-primary

# Optional: Override executable paths if installed in custom directories
# CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
# VSCODE_PATH=C:\Users\<user>\AppData\Local\Programs\Microsoft VS Code\Code.exe

# Allowlist of approved websites for voice opening
APPROVED_WEBSITES=google=https://www.google.com,youtube=https://www.youtube.com,github=https://www.github.com,reddit=https://www.reddit.com,chatgpt=https://chatgpt.com

# Shutdown cancellation safety buffer (seconds)
SHUTDOWN_DELAY_SECONDS=60
```

---

## 4. Local Testing Without Cloud

You can test individual commands directly from your terminal to verify that applications launch and APIs function properly:

```powershell
# Check current session ID, user, and system status
.venv\Scripts\python.exe -m windows_agent.main --status

# List all registered commands and risk levels
.venv\Scripts\python.exe -m windows_agent.main --list-commands

# Test launching Chrome
.venv\Scripts\python.exe -m windows_agent.main --test-command open_chrome

# Test opening an approved website
.venv\Scripts\python.exe -m windows_agent.main --test-command open_website --param website_name=youtube

# Test locking the PC screen
.venv\Scripts\python.exe -m windows_agent.main --test-command lock_pc
```

---

## 5. Starting the Agent

### A. Foreground Console Mode (for debugging)
```powershell
.venv\Scripts\python.exe -m windows_agent.main
```
The agent connects outbound to the cloud broker, registers its session ID, and sends heartbeats every 25 seconds.

### B. Auto-Start on Windows User Login (Recommended)
To ensure the agent launches silently in your interactive desktop session whenever you sign in:

```powershell
# Run the installer script
.venv\Scripts\python.exe scripts\install_startup_task.py
```

This creates a silent VBS launcher (`AlexaWindowsAgent.vbs`) in your Windows User Startup folder:
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`

* Why this is superior to a Windows Service:
  - Windows Services run in **Session 0**, which is isolated from the desktop and cannot display graphical windows.
  - The startup launcher executes in **Session 1+** (your interactive user session), so Chrome and VS Code open visibly on your screen.

---

## 6. Behavior Under Windows System States

| Windows State | What Happens When Voice Command Is Received |
| :--- | :--- |
| **Windows is Locked** | Commands like `lock_pc`, `pc_status`, `shutdown_pc`, `restart_pc`, `cancel_shutdown`, and `sleep_pc` execute normally. GUI applications (Chrome, VS Code) will launch in the background within your user session and will be waiting on your desktop when you unlock. |
| **Windows is Logged Out** | If no user is logged in, the user-session agent is not running. The cloud broker detects that the agent is offline and informs Alexa: *"Your computer is currently offline."* |
| **Computer is Asleep (Sleep / Modern Standby)** | In sleep mode, the CPU and network adapter are powered down. Alexa cannot deliver commands to a sleeping PC unless Wake-on-LAN (WoL) hardware support is configured on your local network. Stale commands queued while sleeping are automatically dropped after 30 seconds (TTL) so they don't fire unexpectedly when you wake the laptop. |
| **Computer is Powered Off** | The cloud broker recognizes the computer is offline and tells Alexa: *"Your computer is currently offline."* Alexa cannot wake a powered-off laptop. |
| **Wi-Fi / Internet Disconnected** | The agent notices the dropped socket and enters an automatic reconnect loop with exponential backoff (1s, 2s, 4s, up to 30s). When internet restores, it reconnects automatically. |
| **Agent Crashes** | Handled exceptions are logged. If configured via Startup launcher, logging is redirected to `logs/agent_startup.log`. |

---

## 7. Uninstalling the Agent

To remove the agent from auto-starting:

```powershell
.venv\Scripts\python.exe scripts\install_startup_task.py uninstall
```
Or run the PowerShell script:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\uninstall_agent.ps1
```
