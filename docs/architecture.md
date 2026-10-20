# System Architecture

## 1. Overview

The **Alexa-to-Windows Command Execution System** is a self-hosted, private alternative to third-party services like TriggerCMD and IFTTT. It enables secure, sub-second voice automation of a Windows 11 laptop through Amazon Alexa smart speakers, without requiring open router ports or inbound public IP addresses.

```
+-------------------------------------------------------------------------------+
|                             SYSTEM TOPOLOGY                                   |
+-------------------------------------------------------------------------------+

 [ Amazon Echo / Alexa Device ]
               |
               | (Spoken: "Alexa, ask My PC to open Chrome")
               v
 [ Amazon Alexa Voice Service ]
               |
               | HTTPS POST (JSON request with cryptographic signature)
               v
 +-----------------------------------------------------------------------------+
 |                         CLOUD COMMAND BROKER                                |
 |                                                                             |
 |  [ /alexa Webhook ]                                                         |
 |        |                                                                    |
 |        +--> Request Verification (ASK Cert Chain, SAN, RSA-SHA256, Replay)  |
 |        |                                                                    |
 |        +--> Intent Mapping & Dialog Confirmation (alexa_handler.py)         |
 |        |                                                                    |
 |  [ Central Queue & Broker ] (command_broker.py)                             |
 |        |                                                                    |
 |        +--> SQLite Persistence (queue_manager.py) & Idempotency Filter     |
 |        |                                                                    |
 |  [ Outbound Gateway ]                                                       |
 |        |                                                                    |
 |        +--> Active WebSocket Hub (/ws/agent)                               |
 |        +--> Fallback HTTP Polling Endpoint (/api/v1/agent/poll)             |
 +-----------------------------------------------------------------------------+
               ^
               |  Outbound Authenticated Connection over TLS
               |  (Persistent WebSocket wss:// + Heartbeat Keep-Alive)
               |  *NO ROUTER PORT FORWARDING REQUIRED*
               v
 +-----------------------------------------------------------------------------+
 |                         WINDOWS 11 LAPTOP                                   |
 |  (Behind Home Wi-Fi Router / NAT)                                           |
 |                                                                             |
 |  [ Windows Command Agent ] (windows_agent/api_client.py)                    |
 |        |                                                                    |
 |        +--> Runs in User Session 1+ (Interactive Desktop Session)          |
 |        |                                                                    |
 |  [ Allowlist Command Registry ] (command_registry.py)                       |
 |        |                                                                    |
 |        +--> Strict Parameter & URL Validation                               |
 |        |                                                                    |
 |  [ Safe Windows Executor ] (executor.py)                                    |
 |        |                                                                    |
 |        +--> Subprocess (shell=False) / Windows Native APIs                  |
 |        |                                                                    |
 |  [ Target Applications & OS ]                                               |
 |        |                                                                    |
 |        +--> Google Chrome (detached GUI process)                            |
 |        +--> Visual Studio Code (detached GUI process)                       |
 |        +--> Default Browser (approved URLs only)                            |
 |        +--> Workstation Lock (user32.dll LockWorkStation)                   |
 |        +--> Scheduled Shutdown / Restart (shutdown.exe with delay & cancel) |
 |        +--> Sleep State (powrprof.dll SetSuspendState)                      |
 +-----------------------------------------------------------------------------+
```

---

## 2. Evaluation of Communication Architectures

Requirement 4 mandates an architecture that operates when the laptop is behind a typical home Wi-Fi router with no public IP and no router port forwarding.

### Evaluation of Options:

| Criterion | Option A: HTTP Polling | Option B: Persistent WebSocket (Selected) | Option C: Inbound Port Forwarding |
| :--- | :--- | :--- | :--- |
| **Firewall / NAT Traversal** | Excellent (outbound GET) | Excellent (outbound TCP/TLS connection) | Poor (requires router port forwarding & dynamic DNS) |
| **Command Delivery Latency** | 1.5s - 3.0s (dependent on poll interval) | **< 50ms (sub-second real-time push)** | < 50ms |
| **Alexa Response Speech** | Difficult to return verified result before Alexa's 8s timeout | **Immediate real-time execution result returned in speech** | Immediate |
| **Server & Network Load** | High (86,400 requests/day at 1s interval) | **Negligible (idle TCP socket with 25s ping/pong)** | Low |
| **Security Risk Profile** | Low | Low (TLS encrypted, authenticated) | **High (exposes local port to public internet scanners)** |
| **Network Failure Recovery** | Automatic retry next poll | Exponential backoff auto-reconnect + HTTP fallback | Fragile on dynamic IP changes |

### Why Persistent WebSocket with HTTP Polling Fallback Was Chosen

1. **Sub-Second Execution**: The Windows agent establishes an outbound connection to the broker (`wss://<domain>/ws/agent`). When an Alexa request arrives, the broker pushes the command down the existing socket in under 50ms.
2. **Immediate Speech Feedback**: Because execution happens in milliseconds, the broker waits synchronously for the agent's acknowledgment and returns honest speech: *"Opening Google Chrome on your computer"* instead of a generic *"Request queued"*.
3. **Zero Router Configuration**: Modern home routers allow outbound TCP connections and maintain NAT state table mappings for active connections. Lightweight ping/pong packets every 25 seconds keep this state alive indefinitely.
4. **Resilience**: If the WebSocket drops (e.g. during a network transition), the agent uses exponential backoff to reconnect and automatically polls the HTTP endpoint `/api/v1/agent/poll` to catch any queued commands.

---

## 3. Windows Session Architecture (Session 1+ vs Session 0)

Windows separates system processes from user interfaces using **Session Isolation**:
* **Session 0**: Reserved exclusively for Windows Services and system background tasks. Session 0 has no interactive desktop and cannot display windows, dialogs, or user interfaces.
* **Session 1+**: Created when a human user signs into Windows. The graphical user interface, desktop, taskbar, and running GUI applications (Chrome, VS Code) reside in this interactive session.

### The Session 0 Pitfall
If a command agent is installed as a standard Windows Service (Session 0), attempting to launch Chrome or VS Code causes the executable to run invisibly in Session 0. The process runs in Task Manager, but no window ever appears on the user's screen.

### Our Solution
The Windows Command Agent runs as a **user-session background process** initiated upon user logon (via the Windows Startup folder or an interactive Task Scheduler entry).
1. `session_manager.py` checks `ProcessIdToSessionId`.
2. It verifies that `session_id > 0` (interactive desktop).
3. Applications are launched with `creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`, ensuring they appear visibly on the user's desktop even if the agent process restarts.

---

## 4. Concurrency and Queue Semantics

Unlike TriggerCMD, this system contains **no 60-second cooldown**:
* Multiple authorized commands can be enqueued and executed in rapid succession (e.g., open Chrome, open VS Code, open YouTube, and lock PC within 2 seconds).
* **FIFO Processing**: Commands are processed in the order received.
* **Idempotency Protection**: Commands support optional client idempotency keys to ensure network retries do not trigger duplicate executions.
* **Time-to-Live (TTL)**: Commands carry an expiration timestamp (default: 30 seconds). If a laptop was asleep or offline, stale commands are discarded automatically upon reconnect rather than executing unexpectedly.
