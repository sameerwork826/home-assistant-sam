# Step-by-Step Alexa Skill Configuration Guide

This guide walks you through creating and configuring your custom Alexa Skill in the official Amazon Developer Console.

---

## 1. Prerequisites

* An [Amazon Developer Account](https://developer.amazon.com/) (free to create).
* An Amazon account linked to your physical Alexa smart speaker (or the Alexa mobile app).
* Your deployed Cloud Broker HTTPS URL (e.g. `https://my-broker.onrender.com` or Cloudflare Tunnel URL).

---

## 2. Create the Custom Skill

1. Sign in to the [Amazon Alexa Developer Console](https://developer.amazon.com/alexa/console/ask).
2. Click the blue **Create Skill** button on the right.
3. In the creation wizard:
   * **Skill name**: `My PC Controller` (or any name you prefer).
   * **Primary locale**: `English (US)` (or your preferred English dialect).
   * **Experience**: Choose **Other**, then select **Custom**.
   * **Hosting service**: Choose **Provision your own** (do NOT choose Alexa-Hosted Python, because Alexa-Hosted functions are short-lived AWS Lambda workers that cannot maintain persistent WebSockets to your laptop).
4. Click **Next** in the top right.
5. On the Template screen, choose **Start from Scratch** and click **Create Skill**.

---

## 3. Set the Invocation Name

1. In the left navigation sidebar, click **Invocations** > **Skill Invocation Name**.
2. Set **Skill Invocation Name** to:
   ```
   my pc
   ```
   *(Amazon rules: Must be 2 or more words, lower case, no punctuation).*
3. Click **Save Model**.

---

## 4. Import the Interaction Model

1. In the left navigation sidebar, navigate to:
   **Interaction Model** > **JSON Editor**.
2. Open the file `alexa_skill/interaction_model/en-US.json` from this repository.
3. Copy its entire JSON content and paste it into the editor box, replacing any existing content.
4. Click **Save Model** at the top.
5. Click **Build Model**. Wait 30–60 seconds until you see the green confirmation banner:
   *"Model building completed successfully."*

---

## 5. Configure the Endpoint

1. In the left navigation sidebar, click **Endpoint**.
2. Select the **HTTPS** radio button.
3. Under **Default Region**, enter your broker's public URL with the `/alexa` path:
   ```
   https://<YOUR-CLOUD-DOMAIN>/alexa
   ```
   *Example: `https://my-pc-broker.onrender.com/alexa`*
4. Under **Select SSL certificate type**, select:
   ```
   My development endpoint is a sub-domain of a domain that has a wildcard certificate from a certificate authority
   ```
   *(This setting is correct for Render, Railway, Fly.io, Cloudflare, Heroku, AWS ALB, etc.)*
5. Click **Save Endpoints** at the top.

---

## 6. Retrieve Your Skill ID

1. In the left navigation sidebar, click **Endpoint** or **Skill Settings**.
2. Locate the **Skill ID** (format: `amzn1.ask.skill.xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`).
3. Copy this value and paste it into your `.env` file as `ALEXA_SKILL_ID`.
4. Redeploy or restart your Cloud Broker so it validates this ID.

---

## 7. Testing Your Skill

### A. Testing in the Developer Console Simulator
1. In the top navigation bar, click the **Test** tab.
2. In the dropdown "Skill testing is enabled in:", change **Off** to **Development**.
3. In the input box on the left, try typing:
   * `open my pc` -> Alexa responds with the welcome message and asks what to do.
   * `ask my pc to open chrome` -> Alexa launches Chrome on your laptop.
   * `ask my pc to check status` -> Alexa reports your laptop's online status and uptime.
   * `ask my pc to shut down my computer` -> Alexa asks for confirmation. Reply: `yes`.

### B. Testing on Your Physical Alexa Device
Because your Amazon Developer account is the same account signed into your physical Echo device, the skill automatically appears under **Your Skills** > **Dev** in your Alexa mobile app!
1. Stand near your smart speaker and say:
   * *"Alexa, ask My PC to open Chrome."*
   * *"Alexa, ask My PC to lock the computer."*
   * *"Alexa, ask My PC for its status."*
2. Commands execute on your laptop in sub-second time!
