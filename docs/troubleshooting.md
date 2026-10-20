# Troubleshooting & Frequently Asked Questions

This guide covers common issues, root causes, and verification steps.

---

## 1. "Your computer is currently offline or unreachable"

### Cause:
The Cloud Command Broker has not received an active WebSocket connection or HTTP heartbeat from your Windows laptop within the last 45 seconds.

### Troubleshooting Steps:
1. **Check Agent Process**: On your laptop, open Task Manager or run:
   ```powershell
   .venv\Scripts\python.exe -m windows_agent.main --status
   ```
   Ensure the agent is running.
2. **Check Authentication Token**: Ensure `AGENT_AUTH_TOKEN` in your laptop's `.env` matches the `AGENT_AUTH_TOKEN` configured in your Cloud Broker environment.
3. **Verify Broker URLs**: Check `BROKER_API_URL` and `BROKER_WS_URL` in `.env`.
   - If using `https://my-broker.onrender.com`, `BROKER_WS_URL` must be `wss://my-broker.onrender.com/ws/agent`.
4. **Inspect Broker Dashboard**: Visit `https://<YOUR-BROKER>/dashboard` and check the **Windows Agents** table. It displays real-time connection status and last-seen timestamps.

---

## 2. Alexa Skill Returns "There was a problem with the requested skill's response"

### Cause:
The Alexa Voice Service received an HTTP error (400, 403, 500) from your `/alexa` endpoint, or the response took longer than 8 seconds.

### Troubleshooting Steps:
1. **Check Amazon Verification Logs**: If `ALEXA_VERIFY_SIGNATURE=true`, the broker validates Amazon's cryptographic signature headers (`SignatureCertChainUrl` and `Signature`). If your test tool didn't pass valid Amazon headers, the request is intentionally rejected with HTTP 400.
2. **Check Skill ID**: If `ALEXA_SKILL_ID` is set in `.env`, verify that the skill ID in the incoming request matches.
3. **Check SSL Certificate**: Alexa requires a valid SSL certificate from a trusted authority. Self-signed certificates are rejected by Amazon. Use Render, Railway, Cloudflare Tunnel, or Let's Encrypt.
4. **Check Endpoint Path**: In the Alexa Developer Console, verify that the Default Region URL ends with `/alexa` (e.g. `https://my-broker.onrender.com/alexa`), not just the root domain.

---

## 3. Chrome or VS Code Does Not Open

### Cause:
The application executable was not found at standard install locations, or was launched in Session 0.

### Troubleshooting Steps:
1. **Run Application Discovery Check**:
   ```powershell
   .venv\Scripts\python.exe -m windows_agent.main --status
   ```
2. **Explicitly Set Executable Path in `.env`**:
   - For Chrome:
     ```ini
     CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
     ```
   - For VS Code:
     ```ini
     VSCODE_PATH=C:\Users\<YourUsername>\AppData\Local\Programs\Microsoft VS Code\Code.exe
     ```
3. **Session Check**: Verify that `is_interactive_session` in `--status` is `True`. If running as a Windows Service (Session 0), applications will run invisibly in the background. Use the user-startup script `scripts/install_agent.ps1` instead.

---

## 4. "Website is not in the approved list"

### Cause:
You requested a website that is not configured in `APPROVED_WEBSITES`. To prevent malicious URL opening, only explicit allowlisted names are permitted.

### Solution:
Open `.env` and add your site to `APPROVED_WEBSITES`:
```ini
APPROVED_WEBSITES=google=https://www.google.com,youtube=https://www.youtube.com,github=https://www.github.com,netflix=https://www.netflix.com
```
Then update your Alexa interaction model in `alexa_skill/interaction_model/en-US.json` to add `netflix` under `PREDEFINED_WEBSITE_TYPE`, save, and click **Build Model**.

---

## 5. PowerShell ExecutionPolicy Error

### Symptom:
```
File ...\profile.ps1 cannot be loaded because running scripts is disabled on this system.
```

### Solution:
Windows default policy disables running unsigned scripts. When executing helper scripts, run with `-ExecutionPolicy Bypass`:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_agent.ps1
```
Alternatively, run python commands directly via `.venv\Scripts\python.exe`.
