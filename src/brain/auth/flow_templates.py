"""Flow Templates — Registration flow templates for typical services.

Does NOT hardcode specific websites, but provides TEMPLATES:
- Generic API Registration
- Generic OAuth2 Registration
- Government Portal Template
- Open Data Portal Template
- Developer Platform Template

Each template is a factory that accepts parameters and returns a RegistrationFlow.
"""

from __future__ import annotations

from src.brain.auth.registration_engine import (
    RegistrationFlow,
    RegistrationStep,
    StepType,
)


def create_api_key_registration(
    *,
    service_id: str,
    service_name: str,
    register_url: str,
    api_key_path: str = "data.api_key",
    extra_fields: dict[str, str] | None = None,
    requires_email_verification: bool = False,
    requires_identity: bool = False,
) -> RegistrationFlow:
    """Template: registration to obtain an API key.

    Typical flow:
    1. POST form with email/name
    2. (Optionally) Confirm email
    3. Extract API key
    4. Save to vault

    Args:
        service_id: Unique ID
        service_name: Service name
        register_url: Registration URL
        api_key_path: JSONPath to API key in response
        extra_fields: Additional form fields
        requires_email_verification: Whether email confirmation is needed
        requires_identity: Whether identity verification is needed
    """
    steps = []

    # Step 1: Collect data from user
    input_fields = [
        {"name": "email", "label": "Email", "type": "email", "required": "true"},
        {"name": "name", "label": "Name", "type": "text", "required": "true"},
    ]
    if extra_fields:
        for name, label in extra_fields.items():
            input_fields.append({"name": name, "label": label, "type": "text", "required": "false"})

    steps.append(
        RegistrationStep(
            name="collect_user_data",
            step_type=StepType.USER_INPUT,
            description="Collecting data for registration",
            input_fields=input_fields,
        )
    )

    # Step 2: Identity verification (if needed)
    if requires_identity:
        steps.append(
            RegistrationStep(
                name="verify_identity",
                step_type=StepType.IDENTITY_VERIFY,
                description="Identity verification",
                identity_context={"action": "register", "service": service_name},
            )
        )

    # Step 3: Submit form
    payload = {"email": "{{email}}", "name": "{{name}}"}
    if extra_fields:
        for name in extra_fields:
            payload[name] = f"{{{{{name}}}}}"

    steps.append(
        RegistrationStep(
            name="submit_registration",
            step_type=StepType.HTTP_JSON,
            description="Submitting registration form",
            url=register_url,
            payload=payload,
        )
    )

    # Step 4: Email verification (if needed)
    if requires_email_verification:
        steps.append(
            RegistrationStep(
                name="wait_email",
                step_type=StepType.USER_INPUT,
                description="Email confirmation",
                input_fields=[
                    {
                        "name": "verification_code",
                        "label": "Verification code from email",
                        "type": "text",
                        "required": "true",
                    },
                ],
            )
        )

    # Step 5: Extract API key
    steps.append(
        RegistrationStep(
            name="extract_api_key",
            step_type=StepType.EXTRACT,
            description="Obtaining API key",
            extract_from="submit_registration",
            extract_path=api_key_path,
            store_as="api_key",
        )
    )

    # Step 6: Save to vault
    steps.append(
        RegistrationStep(
            name="store_credential",
            step_type=StepType.STORE_CREDENTIAL,
            description="Saving API key",
            credential_service=service_id,
            credential_type="api_key",
            credential_data_map={
                "api_key": "{{api_key}}",
                "email": "{{email}}",
            },
        )
    )

    return RegistrationFlow(
        flow_id=f"register_{service_id}",
        service_name=service_name,
        steps=steps,
        requires_identity=requires_identity,
    )


def create_oauth2_registration(
    *,
    service_id: str,
    service_name: str,
    registration_url: str,
    authorize_url: str,
    token_url: str,
    scopes: list[str] | None = None,
    app_name: str = "AtlasTrinity",
    callback_port: int = 8086,
) -> RegistrationFlow:
    """Template: OAuth2 client registration + authorization.

    Flow:
    1. Dynamic Client Registration (RFC 7591)
    2. Authorization Code flow
    3. Save tokens
    """
    callback_url = f"http://localhost:{callback_port}/auth/callback"

    steps = [
        # 1. Dynamic Client Registration
        RegistrationStep(
            name="register_client",
            step_type=StepType.OAUTH_REGISTER,
            description="Registering OAuth2 client",
            url=registration_url,
            payload={
                "client_name": app_name,
                "redirect_uris": [callback_url],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "scope": " ".join(scopes or []),
            },
            callback_port=callback_port,
        ),
        # 2. Extract client_id/secret
        RegistrationStep(
            name="extract_client_id",
            step_type=StepType.EXTRACT,
            description="Obtaining client_id",
            extract_from="register_client",
            extract_path="json.client_id",
            store_as="client_id",
        ),
        RegistrationStep(
            name="extract_client_secret",
            step_type=StepType.EXTRACT,
            description="Obtaining client_secret",
            extract_from="register_client",
            extract_path="json.client_secret",
            store_as="client_secret",
        ),
        # 3. Collect authorization (user redirect)
        RegistrationStep(
            name="user_authorize",
            step_type=StepType.USER_INPUT,
            description="User authorization",
            input_fields=[
                {
                    "name": "authorization_note",
                    "label": (
                        f"Follow the link for authorization:\n"
                        f"{authorize_url}?response_type=code"
                        f"&client_id={{{{client_id}}}}"
                        f"&redirect_uri={callback_url}"
                        f"&scope={'+'.join(scopes or [])}"
                    ),
                    "type": "info",
                    "required": "false",
                },
            ],
        ),
        # 4. Callback listener
        RegistrationStep(
            name="listen_callback",
            step_type=StepType.CALLBACK_LISTEN,
            description="Waiting for callback",
            callback_port=callback_port,
            callback_path="/auth/callback",
            callback_timeout=300,
        ),
        # 5. Exchange code for tokens
        RegistrationStep(
            name="exchange_tokens",
            step_type=StepType.HTTP_JSON,
            description="Exchanging code for tokens",
            url=token_url,
            payload={
                "grant_type": "authorization_code",
                "code": "{{code}}",
                "client_id": "{{client_id}}",
                "client_secret": "{{client_secret}}",
                "redirect_uri": callback_url,
            },
        ),
        # 6. Extract tokens
        RegistrationStep(
            name="extract_access_token",
            step_type=StepType.EXTRACT,
            description="Obtaining access token",
            extract_from="exchange_tokens",
            extract_path="json.access_token",
            store_as="access_token",
        ),
        RegistrationStep(
            name="extract_refresh_token",
            step_type=StepType.EXTRACT,
            description="Obtaining refresh token",
            extract_from="exchange_tokens",
            extract_path="json.refresh_token",
            store_as="refresh_token",
        ),
        # 7. Store in vault
        RegistrationStep(
            name="store_tokens",
            step_type=StepType.STORE_CREDENTIAL,
            description="Saving tokens",
            credential_service=service_id,
            credential_type="oauth2",
            credential_data_map={
                "access_token": "{{access_token}}",
                "refresh_token": "{{refresh_token}}",
                "client_id": "{{client_id}}",
                "client_secret": "{{client_secret}}",
            },
        ),
    ]

    return RegistrationFlow(
        flow_id=f"register_oauth_{service_id}",
        service_name=service_name,
        steps=steps,
    )


def create_web_form_registration(
    *,
    service_id: str,
    service_name: str,
    form_url: str,
    submit_url: str | None = None,
    csrf_selector: str = r'csrf_token["\s]*value="([^"]+)"',
    fields: dict[str, str] | None = None,
    result_extract_path: str | None = None,
    result_extract_regex: str | None = None,
    requires_captcha: bool = False,
    requires_identity: bool = False,
) -> RegistrationFlow:
    """Template: registration via web form.

    Flow:
    1. GET form (extract CSRF token)
    2. Collect data from user
    3. POST form
    4. (Optionally) Solve CAPTCHA
    5. Extract result
    6. Save to vault
    """
    steps = [
        # 1. GET form page
        RegistrationStep(
            name="get_form",
            step_type=StepType.HTTP_GET,
            description="Loading form",
            url=form_url,
        ),
        # 2. Extract CSRF
        RegistrationStep(
            name="extract_csrf",
            step_type=StepType.EXTRACT,
            description="Extracting CSRF token",
            extract_from="get_form",
            extract_regex=csrf_selector,
            store_as="csrf_token",
        ),
    ]

    # 3. User input
    input_fields = []
    for name, label in (fields or {"email": "Email", "password": "Password"}).items():
        input_fields.append({"name": name, "label": label, "type": "text", "required": "true"})

    steps.append(
        RegistrationStep(
            name="collect_data",
            step_type=StepType.USER_INPUT,
            description="Collecting data",
            input_fields=input_fields,
        )
    )

    # 4. Identity verification (optional)
    if requires_identity:
        steps.append(
            RegistrationStep(
                name="verify_identity",
                step_type=StepType.IDENTITY_VERIFY,
                description="Verification",
            )
        )

    # 5. CAPTCHA (optional)
    if requires_captcha:
        steps.append(
            RegistrationStep(
                name="solve_captcha",
                step_type=StepType.CAPTCHA,
                description="CAPTCHA",
                url=form_url,
            )
        )

    # 6. Submit form
    payload = {"csrf_token": "{{csrf_token}}"}
    for name in (fields or {"email": "Email", "password": "Password"}):
        payload[name] = f"{{{{{name}}}}}"

    steps.append(
        RegistrationStep(
            name="submit_form",
            step_type=StepType.HTTP_POST,
            description="Submitting form",
            url=submit_url or form_url,
            payload=payload,
        )
    )

    # 7. Extract result
    if result_extract_path or result_extract_regex:
        steps.append(
            RegistrationStep(
                name="extract_result",
                step_type=StepType.EXTRACT,
                description="Obtaining result",
                extract_from="submit_form",
                extract_path=result_extract_path,
                extract_regex=result_extract_regex,
                store_as="credential_value",
            )
        )

    # 8. Store
    steps.append(
        RegistrationStep(
            name="store_credential",
            step_type=StepType.STORE_CREDENTIAL,
            description="Saving",
            credential_service=service_id,
            credential_type="web_registration",
            credential_data_map={
                "credential": "{{credential_value}}",
                "email": "{{email}}",
            },
        )
    )

    return RegistrationFlow(
        flow_id=f"register_web_{service_id}",
        service_name=service_name,
        service_url=form_url,
        steps=steps,
        requires_identity=requires_identity,
    )


def create_government_portal_registration(
    *,
    service_id: str,
    service_name: str,
    portal_url: str,
    api_registration_url: str | None = None,
    scopes: list[str] | None = None,
    identity_method: str = "dia_eid",
) -> RegistrationFlow:
    """Template: registration on a government portal.

    Flow:
    1. Verification via Diia/BankID
    2. Registration of API keys
    3. Save to vault

    Suitable for: e.land.gov.ua, data.gov.ua, api.nais.gov.ua, etc.
    """
    steps = [
        # 1. Identity verification
        RegistrationStep(
            name="verify_identity",
            step_type=StepType.IDENTITY_VERIFY,
            description=f"Verification via {identity_method}",
            identity_method=identity_method,
            identity_context={
                "action": "register",
                "service": service_name,
                "portal_url": portal_url,
            },
        ),
        # 2. User data collection
        RegistrationStep(
            name="collect_data",
            step_type=StepType.USER_INPUT,
            description="Registration data",
            input_fields=[
                {"name": "app_name", "label": "Application name", "type": "text", "required": "true"},
                {"name": "app_description", "label": "Description", "type": "text", "required": "false"},
                {"name": "contact_email", "label": "Contact email", "type": "email", "required": "true"},
            ],
        ),
    ]

    if api_registration_url:
        steps.append(
            RegistrationStep(
                name="register_api",
                step_type=StepType.HTTP_JSON,
                description="Registering API client",
                url=api_registration_url,
                payload={
                    "name": "{{app_name}}",
                    "description": "{{app_description}}",
                    "email": "{{contact_email}}",
                    "scopes": scopes or [],
                },
            )
        )
        steps.append(
            RegistrationStep(
                name="extract_credentials",
                step_type=StepType.EXTRACT,
                description="Obtaining credentials",
                extract_from="register_api",
                extract_path="json",
                store_as="api_credentials",
            )
        )

    steps.append(
        RegistrationStep(
            name="store_credential",
            step_type=StepType.STORE_CREDENTIAL,
            description="Saving",
            credential_service=service_id,
            credential_type="government_api",
            credential_data_map={
                "credentials": "{{api_credentials}}",
                "portal": portal_url,
                "app_name": "{{app_name}}",
            },
        )
    )

    return RegistrationFlow(
        flow_id=f"register_gov_{service_id}",
        service_name=service_name,
        service_url=portal_url,
        steps=steps,
        requires_identity=True,
        identity_method=identity_method,
    )
