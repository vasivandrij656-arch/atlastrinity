"""Registration Engine — Automatic registration on arbitrary platforms.

Hyper-universal engine: NOT tied to specific websites.
Describe a RegistrationFlow — Atlas executes it automatically.

Supported:
- Web-based registration (HTTP forms)
- API-based registration (REST/GraphQL)
- OAuth2 Dynamic Client Registration (RFC 7591)
- Email verification flows
- Captcha delegation (to user)
- Identity verification via IdentityProvider (Diia, BankID, NFC)

Architecture:
    RegistrationFlow -> set of RegistrationSteps -> sequential execution
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx

logger = logging.getLogger("brain.auth.registration")


class StepType(StrEnum):
    """Registration step types."""

    HTTP_GET = "http_get"  # GET request (get form / csrf token)
    HTTP_POST = "http_post"  # POST request (submit form)
    HTTP_JSON = "http_json"  # POST JSON API
    OAUTH_REGISTER = "oauth_register"  # OAuth2 Dynamic Client Registration
    IDENTITY_VERIFY = "identity_verify"  # Verification via IdentityProvider
    EMAIL_VERIFY = "email_verify"  # Email confirmation
    CAPTCHA = "captcha"  # Captcha (delegated to user)
    USER_INPUT = "user_input"  # Request data from user
    WAIT = "wait"  # Wait N seconds
    EXTRACT = "extract"  # Extract data from previous response
    CONDITIONAL = "conditional"  # Conditional step (if-then)
    STORE_CREDENTIAL = "store_credential"  # Save result to vault
    CALLBACK_LISTEN = "callback_listen"  # Start callback server and wait


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    AWAITING_USER = "awaiting_user"
    SKIPPED = "skipped"


@dataclass
class RegistrationStep:
    """A single registration step.

    Example:
        # POST form with data
        RegistrationStep(
            name="submit_form",
            step_type=StepType.HTTP_POST,
            url="https://example.com/register",
            payload={"email": "{{email}}", "name": "{{name}}"},
        )

        # Extract API key from response
        RegistrationStep(
            name="extract_key",
            step_type=StepType.EXTRACT,
            extract_from="submit_form",
            extract_path="data.api_key",
            store_as="api_key",
        )
    """

    name: str
    step_type: StepType
    description: str = ""

    # HTTP steps
    url: str | None = None
    method: str = "POST"
    payload: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    follow_redirects: bool = True

    # Extract steps
    extract_from: str | None = None  # Name of previous step
    extract_path: str | None = None  # JSONPath-like: "data.api_key"
    extract_regex: str | None = None  # Regex pattern
    store_as: str | None = None  # Variable name to store result

    # Identity verification
    identity_method: str | None = None  # IdentityMethod value
    identity_context: dict[str, Any] | None = None

    # User input
    input_fields: list[dict[str, str]] | None = None  # [{name, label, type, required}]

    # Conditional
    condition: str | None = None  # Python expression with {{variables}}
    then_step: str | None = None
    else_step: str | None = None

    # Callback
    callback_port: int = 8086
    callback_path: str = "/auth/callback"
    callback_timeout: int = 300

    # Wait
    wait_seconds: float = 0

    # Credential storage
    credential_service: str | None = None
    credential_type: str | None = None
    credential_data_map: dict[str, str] | None = None  # {vault_key: "{{variable}}"}

    # Retry
    max_retries: int = 3
    retry_delay: float = 2.0

    # Status tracking
    status: StepStatus = StepStatus.PENDING
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class RegistrationFlow:
    """Complete registration flow for an arbitrary service.

    Example:
        flow = RegistrationFlow(
            flow_id="my_api_registration",
            service_name="My API Service",
            service_url="https://api.example.com",
            steps=[
                RegistrationStep(
                    name="get_csrf",
                    step_type=StepType.HTTP_GET,
                    url="https://api.example.com/register",
                ),
                RegistrationStep(
                    name="extract_csrf",
                    step_type=StepType.EXTRACT,
                    extract_from="get_csrf",
                    extract_regex=r'csrf_token" value="([^"]+)"',
                    store_as="csrf_token",
                ),
                RegistrationStep(
                    name="submit",
                    step_type=StepType.HTTP_POST,
                    url="https://api.example.com/register",
                    payload={
                        "email": "{{email}}",
                        "csrf": "{{csrf_token}}",
                    },
                ),
                RegistrationStep(
                    name="save_result",
                    step_type=StepType.STORE_CREDENTIAL,
                    credential_service="my_api",
                    credential_type="api_key",
                    credential_data_map={"api_key": "{{api_key}}"},
                ),
            ],
        )
    """

    flow_id: str
    service_name: str
    service_url: str = ""
    description: str = ""
    steps: list[RegistrationStep] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)  # Initial variables
    requires_identity: bool = False
    identity_method: str | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class FlowExecutionResult:
    """Flow execution result."""

    flow_id: str
    success: bool
    steps_completed: int
    steps_total: int
    variables: dict[str, Any]
    errors: list[str]
    credentials_stored: list[str]
    duration_seconds: float


class RegistrationEngine:
    """Registration flow execution engine.

    Executes RegistrationFlow step by step, handling different step types.

    Usage:
        engine = RegistrationEngine(vault=vault)

        # Describe a flow
        flow = RegistrationFlow(...)

        # Execute
        result = await engine.execute(flow)
    """

    def __init__(
        self,
        vault: Any | None = None,
        identity_registry: Any | None = None,
    ) -> None:
        from src.brain.auth.credential_vault import CredentialVault

        self._vault = vault or CredentialVault()
        self._identity_registry = identity_registry
        self._http_client: httpx.AsyncClient | None = None
        self._flows: dict[str, RegistrationFlow] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            )
        return self._http_client

    async def close(self) -> None:
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    # ── Flow Management ─────────────────────────────────────────────────

    def register_flow(self, flow: RegistrationFlow) -> None:
        """Registers a flow for later execution."""
        self._flows[flow.flow_id] = flow
        logger.info("📋 Flow registered: %s (%s)", flow.flow_id, flow.service_name)

    def get_flow(self, flow_id: str) -> RegistrationFlow | None:
        return self._flows.get(flow_id)

    def list_flows(self) -> list[str]:
        return list(self._flows.keys())

    # ── Variable Resolution ─────────────────────────────────────────────

    def _resolve_value(self, value: Any, variables: dict[str, Any]) -> Any:
        """Expands {{variable}} placeholders."""
        if isinstance(value, str):
            import re

            def replacer(match: re.Match) -> str:
                var_name = match.group(1).strip()
                return str(variables.get(var_name, match.group(0)))

            return re.sub(r"\{\{(\s*[\w.]+\s*)\}\}", replacer, value)

        if isinstance(value, dict):
            return {k: self._resolve_value(v, variables) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_value(v, variables) for v in value]
        return value

    def _extract_by_path(self, data: Any, path: str) -> Any:
        """Extracts a value from nested dict by dot-notation path."""
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return current

    # ── Step Execution ──────────────────────────────────────────────────

    async def _execute_step(
        self,
        step: RegistrationStep,
        variables: dict[str, Any],
        step_results: dict[str, dict[str, Any]],
    ) -> StepStatus:
        """Executes a single step."""
        step.status = StepStatus.RUNNING
        logger.info("▶️ Step: %s (%s)", step.name, step.step_type.value)

        try:
            if step.step_type == StepType.HTTP_GET:
                return await self._exec_http_get(step, variables, step_results)
            if step.step_type == StepType.HTTP_POST:
                return await self._exec_http_post(step, variables, step_results)
            if step.step_type == StepType.HTTP_JSON:
                return await self._exec_http_json(step, variables, step_results)
            if step.step_type == StepType.EXTRACT:
                return await self._exec_extract(step, variables, step_results)
            if step.step_type == StepType.WAIT:
                return await self._exec_wait(step)
            if step.step_type == StepType.USER_INPUT:
                return await self._exec_user_input(step, variables)
            if step.step_type == StepType.IDENTITY_VERIFY:
                return await self._exec_identity_verify(step, variables)
            if step.step_type == StepType.STORE_CREDENTIAL:
                return await self._exec_store_credential(step, variables)
            if step.step_type == StepType.CONDITIONAL:
                return await self._exec_conditional(step, variables, step_results)
            if step.step_type == StepType.CAPTCHA:
                return await self._exec_captcha(step, variables)
            if step.step_type == StepType.CALLBACK_LISTEN:
                return await self._exec_callback_listen(step, variables)
            if step.step_type == StepType.OAUTH_REGISTER:
                return await self._exec_oauth_register(step, variables)
            step.error = f"Unknown step type: {step.step_type}"
            return StepStatus.FAILED

        except Exception as e:
            step.error = str(e)
            logger.error("❌ Step failed: %s — %s", step.name, e)
            return StepStatus.FAILED

    async def _exec_http_get(
        self,
        step: RegistrationStep,
        variables: dict[str, Any],
        step_results: dict[str, dict[str, Any]],
    ) -> StepStatus:
        url = self._resolve_value(step.url, variables)
        headers = self._resolve_value(step.headers or {}, variables)

        client = await self._get_client()
        resp = await client.get(url, headers=headers)

        step.result = {
            "status_code": resp.status_code,
            "body": resp.text,
            "headers": dict(resp.headers),
        }
        step_results[step.name] = step.result
        step.status = StepStatus.SUCCESS
        return StepStatus.SUCCESS

    async def _exec_http_post(
        self,
        step: RegistrationStep,
        variables: dict[str, Any],
        step_results: dict[str, dict[str, Any]],
    ) -> StepStatus:
        url = self._resolve_value(step.url, variables)
        payload = self._resolve_value(step.payload or {}, variables)
        headers = self._resolve_value(step.headers or {}, variables)

        client = await self._get_client()
        resp = await client.post(url, data=payload, headers=headers)

        step.result = {
            "status_code": resp.status_code,
            "body": resp.text,
            "headers": dict(resp.headers),
        }
        try:
            step.result["json"] = resp.json()
        except Exception:
            pass

        step_results[step.name] = step.result
        step.status = StepStatus.SUCCESS
        return StepStatus.SUCCESS

    async def _exec_http_json(
        self,
        step: RegistrationStep,
        variables: dict[str, Any],
        step_results: dict[str, dict[str, Any]],
    ) -> StepStatus:
        url = self._resolve_value(step.url, variables)
        payload = self._resolve_value(step.payload or {}, variables)
        headers = self._resolve_value(
            step.headers or {"Content-Type": "application/json"}, variables
        )

        client = await self._get_client()
        resp = await client.post(url, json=payload, headers=headers)

        step.result = {
            "status_code": resp.status_code,
            "body": resp.text,
            "headers": dict(resp.headers),
        }
        try:
            step.result["json"] = resp.json()
        except Exception:
            pass

        step_results[step.name] = step.result
        step.status = StepStatus.SUCCESS
        return StepStatus.SUCCESS

    async def _exec_extract(
        self,
        step: RegistrationStep,
        variables: dict[str, Any],
        step_results: dict[str, dict[str, Any]],
    ) -> StepStatus:
        """Extracts data from a previous step's result."""
        source = step_results.get(step.extract_from or "")
        if source is None:
            step.error = f"Source step not found: {step.extract_from}"
            return StepStatus.FAILED

        extracted = None

        # JSONPath extraction
        if step.extract_path:
            data = source.get("json", source)
            extracted = self._extract_by_path(data, step.extract_path)

        # Regex extraction
        if step.extract_regex and not extracted:
            import re

            body = source.get("body", "")
            match = re.search(step.extract_regex, body)
            if match:
                extracted = match.group(1) if match.groups() else match.group(0)

        if extracted is not None and step.store_as:
            variables[step.store_as] = extracted
            step.result = {"extracted": extracted, "stored_as": step.store_as}
            step.status = StepStatus.SUCCESS
            logger.info("📎 Extracted %s = %s...", step.store_as, str(extracted)[:50])
            return StepStatus.SUCCESS

        step.error = "Extraction failed: no data matched"
        return StepStatus.FAILED

    async def _exec_wait(self, step: RegistrationStep) -> StepStatus:
        import asyncio

        await asyncio.sleep(step.wait_seconds)
        step.status = StepStatus.SUCCESS
        return StepStatus.SUCCESS

    async def _exec_user_input(
        self,
        step: RegistrationStep,
        variables: dict[str, Any],
    ) -> StepStatus:
        """Requests data from user.

        In production this will be via UI/TTS/Message Bus.
        Currently — via stdin or pending status.
        """
        step.result = {"fields_needed": step.input_fields}
        step.status = StepStatus.AWAITING_USER
        logger.info("✋ User input needed: %s", [f.get("name") for f in (step.input_fields or [])])
        return StepStatus.AWAITING_USER

    async def _exec_identity_verify(
        self,
        step: RegistrationStep,
        variables: dict[str, Any],
    ) -> StepStatus:
        """Verification via IdentityProvider."""
        if not self._identity_registry:
            step.error = "No identity registry configured"
            return StepStatus.FAILED

        from src.brain.auth.identity_provider import IdentityMethod

        method_str = step.identity_method or variables.get("identity_method", "manual_approval")
        try:
            method = IdentityMethod(method_str)
        except ValueError:
            method = IdentityMethod.MANUAL_APPROVAL

        provider = await self._identity_registry.get_available(method)
        if not provider:
            provider = await self._identity_registry.get_best_available()

        if not provider:
            step.error = "No identity provider available"
            return StepStatus.FAILED

        context = self._resolve_value(step.identity_context or {}, variables)
        challenge = await provider.create_challenge(context)
        step.result = {
            "challenge_id": challenge.challenge_id,
            "instructions": challenge.instructions,
            "deep_link": challenge.deep_link,
            "qr_code_data": challenge.qr_code_data,
        }

        logger.info("🔐 Identity challenge: %s", challenge.instructions)
        step.status = StepStatus.AWAITING_USER
        return StepStatus.AWAITING_USER

    async def _exec_store_credential(
        self,
        step: RegistrationStep,
        variables: dict[str, Any],
    ) -> StepStatus:
        """Stores obtained credential in vault."""
        if not step.credential_service:
            step.error = "No credential_service specified"
            return StepStatus.FAILED

        data_map = step.credential_data_map or {}
        resolved_data = {}
        for vault_key, template in data_map.items():
            resolved_data[vault_key] = self._resolve_value(template, variables)

        self._vault.store(
            service=step.credential_service,
            credential_type=step.credential_type or "custom",
            data=resolved_data,
        )

        step.result = {"service": step.credential_service, "keys": list(resolved_data.keys())}
        step.status = StepStatus.SUCCESS
        logger.info("💾 Credential stored: %s", step.credential_service)
        return StepStatus.SUCCESS

    async def _exec_conditional(
        self,
        step: RegistrationStep,
        variables: dict[str, Any],
        step_results: dict[str, dict[str, Any]],
    ) -> StepStatus:
        """Conditional step."""
        condition = self._resolve_value(step.condition or "False", variables)
        try:
            # Safe condition evaluation
            result = bool(eval(condition, {"__builtins__": {}}, variables))  # noqa: S307  # nosec B307
        except Exception:
            result = False

        step.result = {"condition": condition, "result": result}
        step.status = StepStatus.SUCCESS
        return StepStatus.SUCCESS

    async def _exec_captcha(
        self,
        step: RegistrationStep,
        variables: dict[str, Any],
    ) -> StepStatus:
        """Delegates captcha solving to user."""
        step.result = {
            "message": "CAPTCHA needs to be solved",
            "url": self._resolve_value(step.url, variables),
        }
        step.status = StepStatus.AWAITING_USER
        return StepStatus.AWAITING_USER

    async def _exec_callback_listen(
        self,
        step: RegistrationStep,
        variables: dict[str, Any],
    ) -> StepStatus:
        """Starts a local server for callback."""
        import asyncio

        from fastapi import FastAPI, Request
        from uvicorn import Config, Server

        app = FastAPI()
        received: dict[str, Any] = {}
        event = asyncio.Event()

        @app.get(step.callback_path)
        async def callback(request: Request) -> dict[str, str]:
            params = dict(request.query_params)
            received.update(params)
            event.set()
            return {
                "status": "ok",
                "message": "Atlas received callback. You can close this window.",
            }

        config = Config(app=app, host="0.0.0.0", port=step.callback_port, log_level="warning")  # nosec B104
        server = Server(config)

        # Start server in background
        server_task = asyncio.create_task(server.serve())

        try:
            await asyncio.wait_for(event.wait(), timeout=step.callback_timeout)
            variables.update(received)
            step.result = {"received": received}
            step.status = StepStatus.SUCCESS
            return StepStatus.SUCCESS
        except TimeoutError:
            step.error = "Callback timeout"
            return StepStatus.FAILED
        finally:
            server.should_exit = True
            await server_task

    async def _exec_oauth_register(
        self,
        step: RegistrationStep,
        variables: dict[str, Any],
    ) -> StepStatus:
        """OAuth2 Dynamic Client Registration (RFC 7591)."""
        url = self._resolve_value(step.url, variables)
        payload = self._resolve_value(step.payload or {}, variables)
        headers = self._resolve_value(
            step.headers or {"Content-Type": "application/json"}, variables
        )

        # Default registration payload
        default_payload = {
            "client_name": "AtlasTrinity",
            "redirect_uris": [f"http://localhost:{step.callback_port}{step.callback_path}"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_basic",
        }
        default_payload.update(payload)

        client = await self._get_client()
        resp = await client.post(url, json=default_payload, headers=headers)

        step.result = {
            "status_code": resp.status_code,
        }
        try:
            data = resp.json()
            step.result["json"] = data
            # Store client_id/secret into variables
            if "client_id" in data:
                variables["client_id"] = data["client_id"]
            if "client_secret" in data:
                variables["client_secret"] = data["client_secret"]
        except Exception:
            step.result["body"] = resp.text

        step.status = StepStatus.SUCCESS if resp.status_code < 400 else StepStatus.FAILED
        return step.status

    # ── Flow Execution ──────────────────────────────────────────────────

    async def execute(
        self,
        flow: RegistrationFlow,
        initial_variables: dict[str, Any] | None = None,
    ) -> FlowExecutionResult:
        """Executes a complete registration flow."""
        start_time = time.time()
        variables = {**flow.variables}
        if initial_variables:
            variables.update(initial_variables)

        step_results: dict[str, dict[str, Any]] = {}
        errors: list[str] = []
        credentials_stored: list[str] = []
        completed = 0

        logger.info("🚀 Starting registration flow: %s (%s)", flow.flow_id, flow.service_name)

        for step in flow.steps:
            status = await self._execute_step(step, variables, step_results)

            if status == StepStatus.SUCCESS:
                completed += 1
                if step.step_type == StepType.STORE_CREDENTIAL and step.credential_service:
                    credentials_stored.append(step.credential_service)

            elif status == StepStatus.AWAITING_USER:
                # Stop flow — user action required
                logger.info("⏸️ Flow paused at step: %s (awaiting user)", step.name)
                break

            elif status == StepStatus.FAILED:
                errors.append(f"Step '{step.name}': {step.error}")
                # Retry logic
                retried = False
                for retry in range(step.max_retries - 1):
                    import asyncio

                    await asyncio.sleep(step.retry_delay * (retry + 1))
                    logger.info("🔁 Retry %d/%d for: %s", retry + 2, step.max_retries, step.name)
                    status = await self._execute_step(step, variables, step_results)
                    if status == StepStatus.SUCCESS:
                        completed += 1
                        retried = True
                        break

                if not retried and status != StepStatus.SUCCESS:
                    logger.error("❌ Flow failed at step: %s", step.name)
                    break

        duration = time.time() - start_time
        success = completed == len(flow.steps)

        result = FlowExecutionResult(
            flow_id=flow.flow_id,
            success=success,
            steps_completed=completed,
            steps_total=len(flow.steps),
            variables={k: v for k, v in variables.items() if not k.startswith("_")},
            errors=errors,
            credentials_stored=credentials_stored,
            duration_seconds=duration,
        )

        if success:
            logger.info(
                "✅ Flow completed: %s (%.1fs, %d credentials)",
                flow.flow_id,
                duration,
                len(credentials_stored),
            )
        else:
            logger.warning(
                "⚠️ Flow incomplete: %s (%d/%d steps, %.1fs)",
                flow.flow_id,
                completed,
                len(flow.steps),
                duration,
            )

        return result

    async def resume(
        self,
        flow_id: str,
        user_data: dict[str, Any],
    ) -> FlowExecutionResult:
        """Resumes a flow after user action.

        Args:
            flow_id: Flow ID
            user_data: Data from user (captcha solution, approval, etc.)
        """
        flow = self._flows.get(flow_id)
        if not flow:
            raise ValueError(f"Flow not found: {flow_id}")

        # Merge user data into variables
        flow.variables.update(user_data)

        # Find the awaiting step and mark it as success
        for step in flow.steps:
            if step.status == StepStatus.AWAITING_USER:
                step.status = StepStatus.SUCCESS
                step.result.update(user_data)
                break

        # Re-execute from the next pending step
        return await self.execute(flow, user_data)
