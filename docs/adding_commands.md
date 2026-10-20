# Guide: Adding New Voice Commands

The system is designed with an **Expandable Command Registry** so you can add new commands without modifying the core network broker or transport layer.

Follow this 4-step workflow to add a new command.

---

## Example: Adding "Open Spotify"

We will add a new command: **"Alexa, ask My PC to open Spotify."**

---

### Step 1: Register the Command and Handler in `windows_agent/executor.py`

Open `windows_agent/executor.py`:

1. Add the command definition to `_register_default_commands()`:
```python
# Open Spotify
registry.register(
    CommandDefinition(
        command_id="open_spotify",
        name="Open Spotify",
        description="Launches Spotify desktop player on the interactive desktop",
        intent_mapping="OpenSpotifyIntent",
        risk_level=RiskLevel.LOW,
        timeout_seconds=10.0,
        confirmation_required=False,
        expected_result="Spotify application launched",
        handler=self.execute_open_spotify,
    )
)
```

2. Implement the execution handler in the `WindowsExecutor` class:
```python
def execute_open_spotify(self, params: Dict[str, Any]) -> CommandExecutionResult:
    """Launches Spotify on the interactive desktop."""
    spotify_exe = os.path.expandvars(r"%AppData%\Spotify\Spotify.exe")
    if not os.path.isfile(spotify_exe):
        # Fallback check in PATH or WindowsApps
        import shutil
        found = shutil.which("spotify")
        if found:
            spotify_exe = found
        else:
            return CommandExecutionResult(
                success=False,
                command_id="open_spotify",
                message="Spotify was not found on your computer.",
                error_category="APPLICATION_NOT_FOUND",
            )

    try:
        self._spawn_detached_process([spotify_exe])
        return CommandExecutionResult(
            success=True,
            command_id="open_spotify",
            message="Opening Spotify on your computer.",
        )
    except Exception as ex:
        return CommandExecutionResult(
            success=False,
            command_id="open_spotify",
            message=f"Failed to launch Spotify: {ex}",
            error_category="EXECUTION_ERROR",
        )
```

---

### Step 2: Add Alexa Intent in `alexa_skill/interaction_model/en-US.json`

Open `alexa_skill/interaction_model/en-US.json` and add the new intent to the `"intents"` list:

```json
{
  "name": "OpenSpotifyIntent",
  "slots": [],
  "samples": [
    "open Spotify",
    "launch Spotify",
    "start Spotify",
    "open music",
    "play Spotify on my computer"
  ]
}
```

In the Alexa Developer Console:
1. Paste the updated JSON into **Interaction Model** > **JSON Editor**.
2. Click **Save Model** and **Build Model**.

---

### Step 3: Map Intent in `cloud/alexa_handler.py`

Open `cloud/alexa_handler.py` and add the intent mapping under `_handle_intent()`:

```python
if intent_name == "OpenSpotifyIntent":
    return await self._dispatch_and_respond("open_spotify", {})
```

---

### Step 4: Test Locally

Test the new command immediately on your Windows laptop without connecting to the cloud:

```powershell
.venv\Scripts\python.exe -m windows_agent.main --test-command open_spotify
```

Output:
```
[TEST DISPATCH] Executing: 'open_spotify' with params={}
Success: True
Message: Opening Spotify on your computer.
```

Your new command is now fully integrated and ready to trigger via Alexa!
