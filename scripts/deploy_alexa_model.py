"""
Automated Alexa Interaction Model Deployer.
Pushes the updated alexa_skill/interaction_model/en-US.json directly to the
Amazon Alexa Developer Console using the Skill Management API (SMAPI) or ASK CLI.
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_SKILL_ID = "amzn1.ask.skill.e0eea847-602a-4ce9-bcb5-bb89b07736fc"


def deploy_via_ask_cli(skill_id: str, model_file: Path) -> bool:
    """Deploys interaction model using the official Amazon ASK CLI if installed."""
    ask_bin = shutil.which("ask")
    if not ask_bin:
        return False

    print(f"Found Amazon ASK CLI at: {ask_bin}")
    cmd = [
        ask_bin,
        "smapi",
        "set-interaction-model",
        "--skill-id", skill_id,
        "--stage", "development",
        "--locale", "en-US",
        "--interaction-model", f"file:{model_file}",
    ]
    print(f"Running ASK CLI deployment...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print("[SUCCESS] Interaction model deployed and build triggered via ASK CLI!")
        return True
    else:
        print(f"[WARNING] ASK CLI deployment returned: {res.stderr or res.stdout}")
        return False


def deploy_via_smapi_api(skill_id: str, access_token: str, model_data: dict) -> bool:
    """Deploys interaction model using direct HTTPS request to Amazon SMAPI."""
    import httpx

    url = f"https://api.amazonalexa.com/v1/skills/{skill_id}/stages/development/interactionModel/locales/en-US"
    headers = {
        "Authorization": access_token if access_token.startswith("Bearer ") else f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    print(f"Uploading interaction model directly to Amazon SMAPI: {url}...")
    try:
        res = httpx.put(url, headers=headers, json=model_data, timeout=15.0)
        if res.status_code in [200, 202, 204]:
            print("[SUCCESS] Interaction model successfully uploaded to Amazon Alexa!")
            return True
        else:
            print(f"[ERROR] Amazon SMAPI rejected upload ({res.status_code}): {res.text}")
            return False
    except Exception as ex:
        print(f"[ERROR] SMAPI request failed: {ex}")
        return False


def main():
    from windows_agent.interaction_model_sync import sync_interaction_model

    print("=" * 60)
    print("Alexa Interaction Model Synchronizer & Deployer")
    print("=" * 60)

    # 1. Sync custom commands to local en-US.json
    model_file = PROJECT_ROOT / "alexa_skill" / "interaction_model" / "en-US.json"
    print(f"Synchronizing custom commands into {model_file.name}...")
    updated_model = sync_interaction_model()
    if not updated_model:
        print("[ERROR] Failed to synchronize interaction model.")
        sys.exit(1)

    skill_id = os.getenv("ALEXA_SKILL_ID", DEFAULT_SKILL_ID)
    print(f"Target Skill ID: {skill_id}")

    # 2. Try ASK CLI first
    if deploy_via_ask_cli(skill_id, model_file):
        print("\nAll done! Alexa is now building the updated voice model.")
        return

    # 3. Try direct SMAPI if token provided
    token = os.getenv("ALEXA_API_ACCESS_TOKEN")
    if token:
        if deploy_via_smapi_api(skill_id, token, updated_model):
            print("\nAll done! Alexa is now building the updated voice model.")
            return

    # 4. Fallback instructions: 1-click clipboard copy
    print("\n" + "-" * 60)
    print("HOW TO UPDATE YOUR SKILL IN 1 CLICK (Fastest Method):")
    print("-" * 60)
    print("Because ASK CLI / Amazon API token is not configured on this PC:")
    print("1. Your local 'en-US.json' is ALREADY automatically updated with all your new commands!")
    print("2. In your Windows Agent App > 'Configuration & Endpoints' tab:")
    print("   Click: '[Copy Interaction Model JSON]'")
    print("3. In the Alexa Developer Console:")
    print("   - Go to Build > Interaction Model > JSON Editor")
    print("   - Press Ctrl+A, then Ctrl+V to paste the updated JSON")
    print("   - Click 'Save Model', then click 'Build Model'")
    print("-" * 60)


if __name__ == "__main__":
    main()
