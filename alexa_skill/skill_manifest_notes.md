# Alexa Skill Manifest Configuration Notes

This document provides the exact configuration required when creating or updating the Alexa Skill in the [Amazon Alexa Developer Console](https://developer.amazon.com/alexa/console/ask).

---

## 1. Skill Creation Settings

* **Skill Name**: `My PC Controller` (or any friendly name)
* **Default Language**: `English (US)`
* **Model**: `Custom`
* **Hosting**: `Provision your own` (Select this option so you can point to your own FastAPI HTTPS endpoint).

---

## 2. Invocation Name

* **Skill Invocation Name**: `my pc`
* **Invocation Phrase**: "Alexa, ask My PC to..." / "Alexa, open My PC"

---

## 3. Interaction Model Setup

1. In the Alexa Developer Console, navigate to:
   **Build** > **Interaction Model** > **JSON Editor**.
2. Replace the contents of the editor with the entire contents of:
   `alexa_skill/interaction_model/en-US.json`
3. Click **Save Model**, then click **Build Model**.
4. Wait for the build notification: "Model building completed successfully."

---

## 4. Endpoint Configuration

1. In the Alexa Developer Console, navigate to:
   **Build** > **Endpoint**.
2. Under **Service Endpoint Type**, select **HTTPS**.
3. Under **Default Region**, enter your deployed Cloud Broker URL:
   `https://<YOUR-CLOUD-DOMAIN>/alexa`
   *(Example: `https://my-broker.onrender.com/alexa` or Cloudflare Tunnel URL)*
4. Under **Select SSL certificate type**, choose:
   `My development endpoint is a sub-domain of a domain that has a wildcard certificate from a certificate authority`
   (Standard for Render, Railway, Fly.io, Cloudflare, AWS ALB, etc.)
5. Click **Save Endpoints**.

---

## 5. Security & Verification

* Custom Alexa Skill web services MUST verify that requests genuinely originate from Amazon Alexa.
* Our `cloud/alexa_verification.py` enforces:
  1. `SignatureCertChainUrl` validation (must be HTTPS from `s3.amazonaws.com` on `/echo.api/`).
  2. Subject Alternative Name (`echo-api.amazon.com`).
  3. RSA-SHA256 signature verification over the raw HTTP request body.
  4. Timestamp validation within 150 seconds to prevent replay attacks.
  5. Application ID validation matching `ALEXA_SKILL_ID`.
* For local offline testing, you can temporarily set `ALEXA_VERIFY_SIGNATURE=false` in `.env`.

---

## 6. Testing in Developer Console

1. Navigate to the **Test** tab in the Developer Console.
2. Set "Skill testing is enabled in:" to **Development**.
3. In the Alexa Simulator text box, try typing or speaking:
   * `open my pc`
   * `ask my pc to open chrome`
   * `ask my pc to check status`
   * `ask my pc to lock computer`
   * `ask my pc to shut down computer` -> responds asking for confirmation -> type `yes`
