# Security Architecture and Hardening

Controlling a personal Windows computer remotely requires rigorous defense-in-depth across every network boundary. This document outlines the security controls implemented in this project.

---

## 1. Threat Model & Mitigations

| Threat | Attack Vector | Mitigation Implemented |
| :--- | :--- | :--- |
| **Arbitrary Remote Code Execution (RCE)** | Attacker sends malicious shell command (e.g. `rmdir /s /q C:\`) | **Strict Predefined Allowlist**: The agent only executes hard-coded functions registered in `command_registry.py`. No raw command strings or shell input are ever accepted. Subprocesses are invoked with `shell=False`. |
| **Command Injection via Parameters** | Malicious arguments in slots (e.g. `youtube; calc.exe`) | **Strict Allowlist & Sanitization**: Website opening accepts only approved keys matching `APPROVED_WEBSITES`. Arbitrary URLs or shell metacharacters are rejected. |
| **Unauthorized Broker Access** | Port scanner attempts to enqueue commands | **Token Authentication**: Agent and administrative endpoints require a high-entropy secret bearer token compared using `secrets.compare_digest` to prevent timing attacks. |
| **Forged Alexa Requests** | Attacker sends fake HTTP POST to `/alexa` endpoint | **Amazon ASK Cryptographic Verification**: Verifies `SignatureCertChainUrl` (must be `s3.amazonaws.com` on port 443 with path prefix `/echo.api/`), validates certificate Subject Alternative Name (`echo-api.amazon.com`), and validates RSA-SHA256 signature against raw HTTP request bytes. |
| **Replay Attacks** | Re-transmitting previously recorded requests | **Timestamp Window Check**: Alexa requests must have a timestamp within 150 seconds of current UTC time. Command records enforce a 30-second TTL. |
| **Accidental Destructive Execution** | Ambiguous voice request triggers shutdown | **Two-Step Confirmation**: Shutdown and restart commands require explicit verbal confirmation ("Are you sure you want to shut down? Say yes to confirm"). |
| **Accidental Duplicate Execution** | Network drops causing client to retry POST request | **Idempotency Keys**: Commands track idempotency keys. Repeated submissions within the validity window return the existing command result without re-executing. |
| **Credential Leakage in Logs** | Secrets accidentally printed to stdout or log files | **Sensitive Data Filter**: `SensitiveDataFilter` scrubs bearer tokens, passwords, and secrets from console and file logs. |
| **Denial of Service / Flooding** | Rapid spamming of API endpoints | **Sliding Window Rate Limiter**: Limits requests per IP (120 req/min) without restricting legitimate burst usage. |

---

## 2. Alexa Skills Kit Cryptographic Verification

Amazon requires that all public HTTPS custom skill endpoints verify incoming requests cryptographically. Our implementation in `cloud/alexa_verification.py` enforces the complete official Amazon verification standard:

1. **Certificate URL Validation**:
   - URL scheme must be `https`.
   - Hostname must be `s3.amazonaws.com` (case-insensitive).
   - Port must be `443`.
   - Path must start with `/echo.api/`.
2. **Certificate Properties Check**:
   - Certificate must be currently valid (current time between `not_valid_before` and `not_valid_after`).
   - Subject Alternative Name (SAN) extension must contain `echo-api.amazon.com`.
3. **RSA Signature Verification**:
   - Extracts the public key from the validated certificate.
   - Decodes the `Signature` header from Base64.
   - Verifies the RSA-SHA256 signature against the raw HTTP request body bytes.
4. **Replay Defense**:
   - Inspects `request.timestamp` in the JSON body.
   - Enforces that the drift does not exceed 150 seconds.
5. **Application ID Verification**:
   - Matches `session.application.applicationId` against the configured `ALEXA_SKILL_ID`.

---

## 3. Strict Predefined Command Allowlist

Arbitrary shell execution is completely prevented:

1. **No External Shell Strings**: External requests specify only a `command_id` (e.g. `open_chrome`, `lock_pc`).
2. **No `shell=True`**: All system subprocesses are executed with explicit argument lists (e.g. `["shutdown.exe", "/s", "/t", "60"]`) without invoking `cmd.exe` or `powershell.exe`.
3. **Parameter Allowlisting**: The `open_website` command only accepts site identifiers configured in `APPROVED_WEBSITES` (e.g. `google`, `youtube`, `github`). Passing arbitrary URLs like `http://attacker-site.com` or malicious shell arguments is immediately rejected with an `UNAPPROVED_URL` error.

---

## 4. Secret Management Best Practices

1. **Never Commit Secrets**: The repository includes `.env.example` with dummy values. The `.gitignore` file strictly excludes `.env`, `*.key`, `*.pem`, and `*.db`.
2. **Rotating Tokens**: The agent token can be rotated at any time by updating `AGENT_AUTH_TOKEN` in the `.env` file on both the cloud broker and the Windows laptop, followed by an agent restart.
3. **Zero Windows Credentials**: The system never requires, prompts for, or stores your Windows account password.
