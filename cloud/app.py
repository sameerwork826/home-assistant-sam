"""
Main FastAPI Application for the Cloud Command Broker & Alexa Endpoint.
Mounts REST endpoints, Alexa Skills Kit webhook, and WebSocket server.
"""

import json
import time
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    HTTPException,
    status,
    Query,
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from cloud.config import CloudConfig, get_cloud_config
from cloud.database import Database
from cloud.queue_manager import QueueManager
from cloud.command_broker import CommandBroker
from cloud.alexa_verification import verify_alexa_request
from cloud.alexa_handler import AlexaSkillHandler
from cloud.auth import verify_agent_token, verify_dashboard_auth, rate_limit_dependency
from cloud.models import (
    EnqueueCommandRequest,
    EnqueueCommandResponse,
    AgentResultPayload,
    AgentHeartbeatPayload,
    AgentStatusInfo,
    CommandStatus,
)
from cloud.logging_config import setup_logger

logger = setup_logger("cloud_app")

# Global services singletons
_db: Optional[Database] = None
_queue_manager: Optional[QueueManager] = None
_broker: Optional[CommandBroker] = None
_alexa_handler: Optional[AlexaSkillHandler] = None


def get_services():
    global _db, _queue_manager, _broker, _alexa_handler
    config = get_cloud_config()
    if _db is None:
        _db = Database(config.database_url)
        _queue_manager = QueueManager(
            db=_db,
            default_ttl=config.command_ttl_seconds,
            max_queue_size=config.max_queue_size,
        )
        _broker = CommandBroker(_queue_manager, _db)
        _alexa_handler = AlexaSkillHandler(_broker)
    return _db, _queue_manager, _broker, _alexa_handler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database and dependencies on startup
    db, qm, broker, handler = get_services()
    logger.info("Cloud Command Broker started successfully.")
    yield
    logger.info("Cloud Command Broker shutting down.")


app = FastAPI(
    title="Alexa-to-Windows Command Broker",
    description="Secure command broker and Alexa Skills Kit request handler",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# Health and Diagnostics
# ==============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "alexa-windows-broker",
        "timestamp": time.time(),
    }


@app.get("/", tags=["Root"])
async def root_info():
    return {
        "name": "Alexa-to-Windows Command Broker",
        "version": "1.0.0",
        "docs": "/docs",
        "dashboard": "/dashboard",
        "alexa_endpoint": "/alexa",
    }


# ==============================================================================
# Alexa Skills Kit Webhook Endpoint
# ==============================================================================

@app.post("/alexa", tags=["Alexa"])
async def alexa_webhook(request: Request, config: CloudConfig = Depends(get_cloud_config)):
    """
    Receives and processes incoming Alexa Skills Kit JSON requests.
    Validates Amazon ASK cryptographic signatures unless disabled for development.
    """
    raw_body = await request.body()
    db, qm, broker, alexa_handler = get_services()

    # Cryptographic request verification
    verified_data = await verify_alexa_request(
        request=request,
        raw_body=raw_body,
        expected_skill_id=config.alexa_skill_id,
        enforce_signature=config.alexa_verify_signature,
    )

    # Route and process verified request
    response_payload = await alexa_handler.handle_request(verified_data)
    return response_payload


# ==============================================================================
# Command Enqueueing and Management API
# ==============================================================================

@app.post(
    "/api/v1/commands/enqueue",
    response_model=EnqueueCommandResponse,
    dependencies=[Depends(rate_limit_dependency)],
    tags=["Commands"],
)
async def enqueue_command(
    req: EnqueueCommandRequest,
    agent_id: str = Depends(verify_agent_token),
):
    """Enqueues an authorized predefined command."""
    db, qm, broker, _ = get_services()
    try:
        record = await broker.dispatch_command(
            command_id=req.command_id,
            parameters=req.parameters,
            agent_id=req.agent_id or agent_id,
            wait_for_result=False,
            idempotency_key=req.idempotency_key,
        )
        return EnqueueCommandResponse(
            execution_id=record.execution_id,
            command_id=record.command_id,
            status=record.status,
            message=record.result_message or f"Command '{record.command_id}' enqueued.",
            created_at=record.created_at,
            expires_at=record.expires_at,
        )
    except Exception as ex:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ex))


@app.get("/api/v1/commands/{execution_id}", tags=["Commands"])
async def get_command_status(execution_id: str):
    """Retrieves current status and execution outcome for a command."""
    db, qm, _, _ = get_services()
    cmd = qm.get_command(execution_id)
    if not cmd:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Command not found"
        )
    return cmd


@app.get("/api/v1/commands", tags=["Commands"])
async def list_recent_commands(limit: int = 50):
    """Lists recent commands from the persistent database."""
    db, _, _, _ = get_services()
    return db.get_recent_commands(limit=limit)


# ==============================================================================
# Agent Outbound Polling and Results API
# ==============================================================================

@app.get("/api/v1/agent/poll", tags=["Agent Polling"])
async def agent_poll(
    agent_id: str = Query("windows-laptop-primary"),
    authenticated_agent_id: str = Depends(verify_agent_token),
):
    """
    HTTP Polling fallback endpoint: Windows agent retrieves pending commands.
    """
    db, qm, broker, _ = get_services()
    effective_agent = authenticated_agent_id or agent_id
    broker.record_heartbeat(effective_agent, {}, connected_via="polling")
    pending = qm.get_pending(effective_agent, limit=5)

    commands_payload = []
    for cmd in pending:
        qm.mark_dispatched(cmd.execution_id)
        commands_payload.append({
            "execution_id": cmd.execution_id,
            "command_id": cmd.command_id,
            "parameters": cmd.parameters,
            "created_at": cmd.created_at,
            "expires_at": cmd.expires_at,
        })

    return {"commands": commands_payload}


@app.post("/api/v1/agent/result", tags=["Agent Polling"])
async def agent_report_result(
    payload: AgentResultPayload,
    authenticated_agent_id: str = Depends(verify_agent_token),
):
    """Windows agent reports command execution result via HTTP."""
    db, qm, broker, _ = get_services()
    broker.notify_result_received(
        execution_id=payload.execution_id,
        success=payload.success,
        message=payload.message,
        data=payload.data,
        error_category=payload.error_category,
    )
    return {"status": "recorded"}


@app.post("/api/v1/agent/heartbeat", tags=["Agent Polling"])
async def agent_heartbeat(
    payload: AgentHeartbeatPayload,
    authenticated_agent_id: str = Depends(verify_agent_token),
):
    """Windows agent sends telemetry heartbeat via HTTP."""
    db, qm, broker, _ = get_services()
    broker.record_heartbeat(
        agent_id=payload.agent_id,
        metrics=payload.metrics,
        connected_via="polling",
    )
    return {"status": "acknowledged"}


@app.get("/api/v1/agents", tags=["Agent Polling"])
async def list_agents():
    """Lists registered agents and online/offline status."""
    db, qm, broker, _ = get_services()
    agents = db.list_all_agents()
    return [broker.get_agent_info(a["agent_id"]) for a in agents]


# ==============================================================================
# Persistent WebSocket for Outbound Agent Connection
# ==============================================================================

@app.websocket("/ws/agent")
async def agent_websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    config: CloudConfig = Depends(get_cloud_config),
):
    """
    Persistent outbound WebSocket connection initiated by the Windows Agent.
    Sub-second command push, heartbeat telemetry, and immediate result returns.
    """
    # Authenticate token from query parameter or headers
    auth_header = websocket.headers.get("authorization", "")
    bearer_token = auth_header.replace("Bearer ", "").strip() if auth_header else ""
    provided_token = token or bearer_token

    if not provided_token or provided_token != config.agent_auth_token:
        logger.warning("Rejected WebSocket connection: invalid authentication token.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    agent_id = websocket.headers.get("x-agent-id", "windows-laptop-primary")
    await websocket.accept()

    db, qm, broker, _ = get_services()
    broker.register_websocket(agent_id, websocket)

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                data = json.loads(raw_text)
                action = data.get("action")

                if action in ["heartbeat", "register"]:
                    metrics = data.get("metrics", {})
                    broker.record_heartbeat(agent_id, metrics, connected_via="websocket")

                elif action == "command_result":
                    execution_id = data.get("execution_id", "")
                    success = data.get("success", False)
                    message = data.get("message", "")
                    res_data = data.get("data")
                    err_category = data.get("error_category")

                    broker.notify_result_received(
                        execution_id=execution_id,
                        success=success,
                        message=message,
                        data=res_data,
                        error_category=err_category,
                    )

                elif action == "pong":
                    broker.record_heartbeat(agent_id, {}, connected_via="websocket")

            except Exception as parse_err:
                logger.error(f"Error parsing WebSocket payload: {parse_err}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket client '{agent_id}' disconnected.")
    finally:
        broker.unregister_websocket(agent_id)


# ==============================================================================
# Minimal Web Dashboard
# ==============================================================================

@app.get(
    "/dashboard",
    response_class=HTMLResponse,
    dependencies=[Depends(verify_dashboard_auth)],
    tags=["Dashboard"],
)
async def dashboard():
    """
    Minimal local web dashboard displaying agent connectivity,
    queue status, and command execution history.
    """
    db, qm, broker, _ = get_services()
    agents = db.list_all_agents()
    agent_info_list = [broker.get_agent_info(a["agent_id"]) for a in agents]
    recent_cmds = db.get_recent_commands(limit=25)

    agent_cards_html = ""
    for info in agent_info_list:
        badge_color = "#10b981" if info.is_online else "#ef4444"
        badge_text = "ONLINE" if info.is_online else "OFFLINE"
        metrics = info.metrics or {}
        agent_cards_html += f"""
        <div class="card">
            <div class="card-header">
                <h3>{info.agent_id}</h3>
                <span class="badge" style="background-color: {badge_color};">{badge_text}</span>
            </div>
            <p><strong>Connection:</strong> {info.connected_via.upper()}</p>
            <p><strong>Last Seen:</strong> {info.last_seen_seconds_ago:.1f}s ago</p>
            <p><strong>OS:</strong> {metrics.get('os', 'Unknown')}</p>
            <p><strong>User:</strong> {metrics.get('username', 'Unknown')}</p>
            <p><strong>Uptime:</strong> {metrics.get('uptime_formatted', 'Unknown')}</p>
            <p><strong>Lock State:</strong> {'Locked' if info.is_locked else 'Unlocked'}</p>
        </div>
        """

    if not agent_cards_html:
        agent_cards_html = "<p class='empty-text'>No Windows agents registered yet. Start the agent locally to see it connect.</p>"

    cmd_rows_html = ""
    for cmd in recent_cmds:
        status_colors = {
            "succeeded": "#10b981",
            "failed": "#ef4444",
            "queued": "#f59e0b",
            "dispatched": "#3b82f6",
            "expired": "#6b7280",
        }
        color = status_colors.get(cmd.status.value, "#6b7280")
        created_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(cmd.created_at))
        cmd_rows_html += f"""
        <tr>
            <td><code>{cmd.execution_id[:8]}...</code></td>
            <td><strong>{cmd.command_id}</strong></td>
            <td><span class="badge" style="background-color: {color};">{cmd.status.value.upper()}</span></td>
            <td>{created_time}</td>
            <td>{cmd.result_message or '-'}</td>
        </tr>
        """

    if not cmd_rows_html:
        cmd_rows_html = "<tr><td colspan='5' class='empty-text'>No commands executed yet.</td></tr>"

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Alexa-to-Windows Command Broker</title>
        <style>
            :root {{
                --bg: #0f172a;
                --surface: #1e293b;
                --text: #f8fafc;
                --text-muted: #94a3b8;
                --accent: #38bdf8;
                --border: #334155;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-color: var(--bg);
                color: var(--text);
                margin: 0;
                padding: 2rem;
            }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            h1, h2, h3 {{ margin-top: 0; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 1rem; margin-bottom: 2rem; }}
            .badge {{ display: inline-block; padding: 0.25rem 0.6rem; border-radius: 9999px; font-size: 0.75rem; font-weight: bold; color: white; }}
            .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }}
            .card {{ background-color: var(--surface); border: 1px solid var(--border); border-radius: 0.75rem; padding: 1.25rem; }}
            .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }}
            table {{ width: 100%; border-collapse: collapse; background-color: var(--surface); border-radius: 0.75rem; overflow: hidden; }}
            th, td {{ padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--border); font-size: 0.9rem; }}
            th {{ background-color: #273549; color: var(--accent); }}
            .empty-text {{ text-align: center; color: var(--text-muted); padding: 1.5rem; }}
            code {{ background: #0f172a; padding: 0.2rem 0.4rem; border-radius: 4px; font-size: 0.85em; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div>
                    <h1>Alexa-to-Windows Command Broker</h1>
                    <p style="color: var(--text-muted); margin: 0;">Alternative to TriggerCMD &bull; Real-Time Voice Automation</p>
                </div>
                <div>
                    <span class="badge" style="background-color: #3b82f6;">FASTAPI &bull; WEBSOCKET</span>
                </div>
            </div>

            <h2>Windows Agents</h2>
            <div class="grid">
                {agent_cards_html}
            </div>

            <h2>Recent Command Execution History</h2>
            <table>
                <thead>
                    <tr>
                        <th>Execution ID</th>
                        <th>Command ID</th>
                        <th>Status</th>
                        <th>Timestamp</th>
                        <th>Result / Message</th>
                    </tr>
                </thead>
                <tbody>
                    {cmd_rows_html}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    return html
