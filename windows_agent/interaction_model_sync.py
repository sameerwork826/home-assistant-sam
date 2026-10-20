"""
Automatic Alexa Interaction Model Synchronizer.
Synchronizes user-defined custom commands from custom_commands.json into
alexa_skill/interaction_model/en-US.json so new voice triggers, website slots,
and utterances are always aligned.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def find_model_path() -> Path:
    """Finds the en-US.json interaction model file across frozen and script environments."""
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates.append(exe_dir / "alexa_skill" / "interaction_model" / "en-US.json")
        if hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "alexa_skill" / "interaction_model" / "en-US.json")
        candidates.append(exe_dir.parent.parent / "alexa_skill" / "interaction_model" / "en-US.json")

    candidates.extend([
        PROJECT_ROOT / "alexa_skill" / "interaction_model" / "en-US.json",
        Path.cwd() / "alexa_skill" / "interaction_model" / "en-US.json",
    ])

    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def find_custom_commands_path() -> Path:
    """Finds the custom_commands.json file across frozen and script environments."""
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates.append(exe_dir / "custom_commands.json")
        if hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "custom_commands.json")

    candidates.extend([
        PROJECT_ROOT / "custom_commands.json",
        Path.cwd() / "custom_commands.json",
    ])

    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def sync_interaction_model(
    custom_commands_path: Optional[Path] = None,
    model_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Syncs all custom commands into the Alexa interaction model JSON:
    1. Adds custom web triggers to PREDEFINED_WEBSITE_TYPE with voice synonyms.
    2. Adds carrier utterances (open/launch/run/start/play/trigger {CommandName}) to RunCustomCommandIntent.
    """
    cmd_file = custom_commands_path or find_custom_commands_path()
    model_file = model_path or find_model_path()

    if not cmd_file.exists() or not model_file.exists():
        return {}

    try:
        with open(cmd_file, "r", encoding="utf-8") as f:
            custom_cmds = json.load(f)

        with open(model_file, "r", encoding="utf-8") as f:
            model = json.load(f)

        # 1. Update PREDEFINED_WEBSITE_TYPE with custom URL commands
        types = model.get("interactionModel", {}).get("languageModel", {}).get("types", [])
        website_type = next((t for t in types if t.get("name") == "PREDEFINED_WEBSITE_TYPE"), None)

        if website_type:
            existing_ids = {v["id"].lower() for v in website_type.get("values", [])}
            for cmd in custom_cmds:
                cmd_line = cmd.get("command_line", "").lower()
                trigger = cmd.get("trigger_name", "").lower().strip()
                if cmd_line.startswith(("http://", "https://", "www.")):
                    clean_id = trigger.replace(" ", "_").replace("open_", "").replace("open ", "")
                    if clean_id not in existing_ids:
                        website_type["values"].append({
                            "id": clean_id,
                            "name": {
                                "value": trigger,
                                "synonyms": [
                                    trigger,
                                    clean_id,
                                    f"{clean_id} dot com",
                                    f"open {clean_id}",
                                    f"go to {clean_id}",
                                ],
                            },
                        })
                        existing_ids.add(clean_id)

        # 2. Ensure RunCustomCommandIntent has rich carrier utterances
        intents = model.get("interactionModel", {}).get("languageModel", {}).get("intents", [])
        custom_intent = next((i for i in intents if i.get("name") == "RunCustomCommandIntent"), None)

        if custom_intent:
            carrier_samples = {
                "run {CommandName}",
                "trigger {CommandName}",
                "execute {CommandName}",
                "start {CommandName}",
                "launch {CommandName}",
                "open {CommandName}",
                "play {CommandName}",
                "run the command {CommandName}",
                "run command {CommandName}",
                "trigger command {CommandName}",
                "execute command {CommandName}",
                "open website {CommandName}",
                "open app {CommandName}",
                "start app {CommandName}",
            }
            existing_samples = set(custom_intent.get("samples", []))
            custom_intent["samples"] = sorted(list(existing_samples.union(carrier_samples)))

        with open(model_file, "w", encoding="utf-8") as f:
            json.dump(model, f, indent=2)

        return model
    except Exception as ex:
        print(f"Failed to sync interaction model: {ex}")
        return {}


def get_interaction_model_json_string() -> str:
    """Returns the formatted JSON content of the interaction model."""
    model_file = find_model_path()
    if model_file.exists():
        try:
            return model_file.read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


if __name__ == "__main__":
    updated = sync_interaction_model()
    print(f"Interaction model synchronized successfully. Total intents: {len(updated.get('interactionModel', {}).get('languageModel', {}).get('intents', []))}")
