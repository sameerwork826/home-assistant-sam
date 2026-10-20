"""
Alexa Skills Kit Request and Intent Handler.
Processes LaunchRequest, IntentRequest, and SessionEndedRequest.
Handles confirmation flows for high-risk actions, slot extraction,
and returns compliant Alexa response payloads.
"""

from typing import Dict, Any, Optional
from cloud.command_broker import CommandBroker
from cloud.models import CommandStatus
from cloud.logging_config import setup_logger

logger = setup_logger("alexa_handler")


def build_alexa_response(
    speech_text: str,
    reprompt_text: Optional[str] = None,
    should_end_session: bool = True,
    card_title: str = "My PC",
    session_attributes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generates standard Amazon Alexa Skills Kit JSON response payload."""
    response: Dict[str, Any] = {
        "version": "1.0",
        "sessionAttributes": session_attributes or {},
        "response": {
            "outputSpeech": {
                "type": "PlainText",
                "text": speech_text,
            },
            "card": {
                "type": "Simple",
                "title": card_title,
                "content": speech_text,
            },
            "shouldEndSession": should_end_session,
        },
    }

    if reprompt_text and not should_end_session:
        response["response"]["reprompt"] = {
            "outputSpeech": {
                "type": "PlainText",
                "text": reprompt_text,
            }
        }

    return response


class AlexaSkillHandler:
    """Processes verified Alexa Skill requests and interfaces with CommandBroker."""

    def __init__(self, broker: CommandBroker) -> None:
        self.broker = broker

    async def handle_request(self, alexa_json: Dict[str, Any]) -> Dict[str, Any]:
        """Routes Alexa JSON request to the appropriate handler."""
        request_obj = alexa_json.get("request", {})
        request_type = request_obj.get("type", "")
        session = alexa_json.get("session", {})
        session_attrs = session.get("attributes", {})

        logger.info(f"Received Alexa request type: '{request_type}'")

        if request_type == "LaunchRequest":
            return self._handle_launch()

        elif request_type == "IntentRequest":
            return await self._handle_intent(request_obj, session_attrs)

        elif request_type == "SessionEndedRequest":
            return self._handle_session_ended(request_obj)

        return build_alexa_response(
            "Unsupported request type received by My PC skill.",
            should_end_session=True,
        )

    def _handle_launch(self) -> Dict[str, Any]:
        """Handles invocation without intent: 'Alexa, open My PC'."""
        welcome = (
            "Welcome to My PC. You can ask me to open Chrome, open VS Code, "
            "lock the computer, put the computer to sleep, or check status. "
            "What would you like to do?"
        )
        reprompt = "What would you like me to do on your computer?"
        return build_alexa_response(
            speech_text=welcome,
            reprompt_text=reprompt,
            should_end_session=False,
            card_title="My PC - Ready",
        )

    async def _handle_intent(
        self, request_obj: Dict[str, Any], session_attrs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handles specific user intents."""
        intent = request_obj.get("intent", {})
        intent_name = intent.get("name", "")
        slots = intent.get("slots", {})
        dialog_state = request_obj.get("dialogState")
        intent_confirmation = intent.get("confirmationStatus")

        logger.info(f"Processing Intent: '{intent_name}' (confirmation: {intent_confirmation})")

        # Built-in Amazon Intents
        if intent_name in ["AMAZON.CancelIntent", "AMAZON.StopIntent"]:
            return build_alexa_response("Goodbye.", should_end_session=True)

        if intent_name == "AMAZON.HelpIntent":
            help_text = (
                "You can say: open Chrome, open VS Code, lock the computer, "
                "open YouTube, check status, or put the computer to sleep. "
                "What would you like to do?"
            )
            return build_alexa_response(
                help_text,
                reprompt_text="What would you like to do?",
                should_end_session=False,
            )

        if intent_name == "AMAZON.FallbackIntent":
            fallback_text = (
                "Sorry, I didn't recognize that command for My PC. "
                "You can ask me to open Chrome, lock the computer, or check PC status."
            )
            return build_alexa_response(
                fallback_text,
                reprompt_text="Would you like to try another command?",
                should_end_session=False,
            )

        # Confirm / Cancel Action for High-Risk Commands
        if intent_name in ["ConfirmActionIntent", "AMAZON.YesIntent"]:
            pending = session_attrs.get("pending_action")
            if pending in ["shutdown_pc", "restart_pc"]:
                return await self._dispatch_and_respond(pending, {})
            else:
                return build_alexa_response(
                    "There is no action waiting for confirmation.",
                    should_end_session=True,
                )

        if intent_name in ["CancelActionIntent", "AMAZON.NoIntent"]:
            pending = session_attrs.get("pending_action")
            if pending:
                return build_alexa_response("Action cancelled.", should_end_session=True)
            return build_alexa_response("Okay.", should_end_session=True)

        # High-Risk Commands Requiring Confirmation
        if intent_name == "ShutdownPCIntent":
            if intent_confirmation == "CONFIRMED":
                return await self._dispatch_and_respond("shutdown_pc", {})
            elif intent_confirmation == "DENIED":
                return build_alexa_response("Shutdown cancelled.", should_end_session=True)
            else:
                # Prompt confirmation
                prompt = "Are you sure you want to shut down your computer? Say yes to confirm or no to cancel."
                return build_alexa_response(
                    prompt,
                    reprompt_text="Say yes to shut down, or no to cancel.",
                    should_end_session=False,
                    session_attributes={"pending_action": "shutdown_pc"},
                )

        if intent_name == "RestartPCIntent":
            if intent_confirmation == "CONFIRMED":
                return await self._dispatch_and_respond("restart_pc", {})
            elif intent_confirmation == "DENIED":
                return build_alexa_response("Restart cancelled.", should_end_session=True)
            else:
                prompt = "Are you sure you want to restart your computer? Say yes to confirm or no to cancel."
                return build_alexa_response(
                    prompt,
                    reprompt_text="Say yes to restart, or no to cancel.",
                    should_end_session=False,
                    session_attributes={"pending_action": "restart_pc"},
                )

        # Direct Predefined Commands
        if intent_name == "OpenChromeIntent":
            return await self._dispatch_and_respond("open_chrome", {})

        if intent_name == "OpenVSCodeIntent":
            return await self._dispatch_and_respond("open_vscode", {})

        if intent_name == "OpenWebsiteIntent":
            website_slot = slots.get("WebsiteName") or slots.get("website_name") or {}
            site_value = website_slot.get("value")
            # If resolution values are present, prefer resolved value
            resolutions = (
                website_slot.get("resolutions", {})
                .get("resolutionsPerAuthority", [{}])[0]
                .get("values", [{}])[0]
                .get("value", {})
                .get("name")
            )
            chosen_site = resolutions or site_value

            if not chosen_site:
                return build_alexa_response(
                    "Which website would you like to open? For example, YouTube, Google, or GitHub.",
                    reprompt_text="Which website should I open?",
                    should_end_session=False,
                )

            return await self._dispatch_and_respond(
                "open_website", {"website_name": chosen_site}
            )

        if intent_name == "LockPCIntent":
            return await self._dispatch_and_respond("lock_pc", {})

        if intent_name == "SleepPCIntent":
            return await self._dispatch_and_respond("sleep_pc", {})

        if intent_name == "CancelShutdownIntent":
            return await self._dispatch_and_respond("cancel_shutdown", {})

        if intent_name == "PCStatusIntent":
            return await self._dispatch_and_respond("pc_status", {})

        if intent_name == "CommandStatusIntent":
            return await self._dispatch_and_respond("command_status", {})

        if intent_name == "RunCustomCommandIntent":
            cmd_slot = slots.get("CommandName") or slots.get("command_name") or {}
            cmd_name = cmd_slot.get("value")
            if not cmd_name:
                return build_alexa_response(
                    "Which custom command would you like me to run?",
                    reprompt_text="Which command should I run on your computer?",
                    should_end_session=False,
                )
            return await self._dispatch_and_respond(
                "run_custom", {"command_name": cmd_name}
            )

        return build_alexa_response(
            f"Command for intent '{intent_name}' is not recognized.",
            should_end_session=True,
        )

    async def _dispatch_and_respond(
        self,
        command_id: str,
        params: Dict[str, Any],
        agent_id: str = "windows-laptop-primary",
    ) -> Dict[str, Any]:
        """Dispatches command to broker and translates outcome to natural Alexa speech."""
        # Check if agent is currently reachable
        if not self.broker.is_agent_online(agent_id):
            return build_alexa_response(
                "Your computer is currently offline or unreachable. "
                "Please verify that your PC is turned on and the agent is running.",
                should_end_session=True,
            )

        # Dispatch command with synchronous wait window (up to 5.0s)
        record = await self.broker.dispatch_command(
            command_id=command_id,
            parameters=params,
            agent_id=agent_id,
            wait_for_result=True,
            wait_timeout=5.0,
        )

        if record.status == CommandStatus.SUCCEEDED:
            msg = record.result_message or f"Command '{command_id}' completed successfully."
            return build_alexa_response(msg, should_end_session=True)

        elif record.status == CommandStatus.FAILED:
            msg = record.result_message or f"Command '{command_id}' failed to execute."
            return build_alexa_response(msg, should_end_session=True)

        elif record.status == CommandStatus.DISPATCHED:
            # Operation was sent but took longer than 5 seconds (e.g. slow launch)
            return build_alexa_response(
                f"Command '{command_id}' was sent to your computer and is processing.",
                should_end_session=True,
            )

        else:
            return build_alexa_response(
                f"Command '{command_id}' is queued for execution.",
                should_end_session=True,
            )

    def _handle_session_ended(self, request_obj: Dict[str, Any]) -> Dict[str, Any]:
        """Handles SessionEndedRequest."""
        reason = request_obj.get("reason", "USER_INITIATED")
        logger.info(f"Alexa session ended. Reason: {reason}")
        return {"version": "1.0", "response": {}}
