#!/usr/bin/env python3
"""Automates Auth0 resource setup described in docs/AUTH0.md.

Run with:
    python scripts/setup_auth0.py
    just setup-auth0
"""

import getpass
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
FRONTEND_ENV_FILE = ROOT / "frontend" / ".env"


# ── Helpers ────────────────────────────────────────────────────────────────────


def check_auth0_cli() -> None:
    if not shutil.which("auth0"):
        print("Error: auth0 CLI not found.")
        print("\nInstall it:")
        print("  Windows (Scoop):      scoop install auth0")
        print("  macOS/Linux (Brew):   brew install auth0/auth0-cli/auth0")
        print("  Manual download:      https://github.com/auth0/auth0-cli/releases")
        sys.exit(1)

    # Check if already logged in
    result = run("auth0", "tenants", "list", check=False)
    if result.returncode != 0:
        print("You are not logged in to the Auth0 CLI.")
        answer = input("Run 'auth0 login' now? [Y/n]: ").strip().lower()
        if answer != "n":
            login_result = subprocess.run(
                [
                    "auth0",
                    "login",
                    "--scopes",
                    "create:client_grants,read:users,update:users,delete:users",
                ],
            )
            if login_result.returncode != 0:
                print("Login failed. Please try manually:")
                print(
                    "  auth0 login --scopes create:client_grants,read:users,update:users,delete:users"
                )
                sys.exit(1)
        else:
            print("Please log in first with:")
            print("  auth0 login --scopes create:client_grants,read:users,update:users,delete:users")
            sys.exit(1)


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(list(args), capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"\nCommand failed: {' '.join(args)}")
        print(f"stderr: {result.stderr.strip()}")
        sys.exit(1)
    return result


def run_json(*args: str) -> dict[str, Any]:
    """Run a command, appending --json, and return parsed output."""
    result = run(*args, "--json")
    try:
        data: dict[str, Any] = json.loads(result.stdout)
        return data
    except json.JSONDecodeError:
        print(f"Failed to parse JSON:\n{result.stdout}")
        sys.exit(1)


def prompt(message: str, default: str | None = None, secret: bool = False) -> str:
    display = f"{message} [{default}]: " if default else f"{message}: "
    value = getpass.getpass(display) if secret else input(display).strip()
    if not value:
        if default:
            return default
        print(f"Error: {message} is required.")
        sys.exit(1)
    return value


def step(n: int, title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  Step {n}: {title}")
    print("─" * 60)


# ── Env file helpers ───────────────────────────────────────────────────────────


def update_env(path: Path, updates: dict[str, str]) -> None:
    """Update or add key=value pairs in an env file."""
    if not path.exists():
        # Create from example if present
        example = path.parent / (path.name + ".example")
        if example.exists():
            import shutil as _shutil

            _shutil.copy(example, path)
            print(f"  Created {path.name} from {example.name}")
        else:
            path.touch()

    lines = path.read_text(encoding="utf-8").splitlines()
    updated: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                updated.add(key)
                continue
        new_lines.append(line)

    # Append any keys not already present
    for key, value in updates.items():
        if key not in updated:
            new_lines.append(f"{key}={value}")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"  Updated {path.relative_to(ROOT)}")


# ── Tenant detection ───────────────────────────────────────────────────────────


def detect_tenant() -> str | None:
    result = run("auth0", "tenants", "list", "--json", check=False)
    if result.returncode != 0:
        return None
    try:
        tenants: list[dict[str, Any]] = json.loads(result.stdout)
        if not tenants:
            return None
        active = next((t for t in tenants if t.get("active")), tenants[0])
        # CLI versions differ: some use "name", some use "domain"
        domain: str = active.get("domain") or active.get("name") or ""
        # Ensure it looks like a domain (contains a dot)
        return domain if "." in domain else None
    except (json.JSONDecodeError, KeyError, IndexError):
        return None


def validate_tenant_login(tenant_domain: str) -> None:
    """Confirm the CLI is logged in and active for the given tenant domain."""
    result = run("auth0", "tenants", "list", "--json", check=False)
    if result.returncode != 0:
        print("  Warning: Could not verify CLI login — proceeding anyway.")
        return
    try:
        tenants: list[dict[str, Any]] = json.loads(result.stdout)
        active = next((t for t in tenants if t.get("active")), None)
        active_domain: str = active.get("name", "") if active else ""
        if active_domain and active_domain != tenant_domain:
            print(f"\nWarning: the Auth0 CLI is logged in to '{active_domain}',")
            print(f"         but you entered '{tenant_domain}'.")
            print("         Resources will be created under the CLI's active tenant.")
            confirm = input("Continue anyway? [y/N]: ").strip().lower()
            if confirm != "y":
                print("Aborted.")
                sys.exit(0)
        else:
            print(f"  Verified: CLI is logged in to '{tenant_domain}'")
    except (json.JSONDecodeError, KeyError, TypeError):
        print("  Warning: Could not verify CLI login — proceeding anyway.")


# ── Resource lookup helpers ────────────────────────────────────────────────────


def find_existing_api(identifier: str) -> dict[str, Any] | None:
    result = run("auth0", "apis", "list", "--json", check=False)
    if result.returncode != 0:
        return None
    try:
        apis: list[dict[str, Any]] = json.loads(result.stdout)
        return next((a for a in apis if a.get("identifier") == identifier), None)
    except (json.JSONDecodeError, TypeError):
        return None


def find_existing_app(name: str) -> dict[str, Any] | None:
    result = run("auth0", "apps", "list", "--json", check=False)
    if result.returncode != 0:
        return None
    try:
        apps: list[dict[str, Any]] = json.loads(result.stdout)
        return next((a for a in apps if a.get("name") == name), None)
    except (json.JSONDecodeError, TypeError):
        return None


def find_existing_role(name: str) -> dict[str, Any] | None:
    result = run("auth0", "roles", "list", "--json", check=False)
    if result.returncode != 0:
        return None
    try:
        roles: list[dict[str, Any]] = json.loads(result.stdout)
        return next((r for r in roles if r.get("name") == name), None)
    except (json.JSONDecodeError, TypeError):
        return None


def find_existing_user(email: str) -> dict[str, Any] | None:
    result = run(
        "auth0", "users", "search", "--query", f"email:{email}", "--json", check=False
    )
    if result.returncode != 0:
        return None
    try:
        users: list[dict[str, Any]] = json.loads(result.stdout)
        return next(
            (u for u in users if u.get("email", "").lower() == email.lower()), None
        )
    except (json.JSONDecodeError, TypeError):
        return None


def find_existing_action(name: str) -> dict[str, Any] | None:
    result = run("auth0", "actions", "list", "--json", check=False)
    if result.returncode != 0:
        return None
    try:
        data: dict[str, Any] | list[dict[str, Any]] = json.loads(result.stdout)
        # Auth0 CLI may return a list or {"actions": [...]}
        actions: list[dict[str, Any]] = (
            data if isinstance(data, list) else data.get("actions", [])
        )
        return next((a for a in actions if a.get("name") == name), None)
    except (json.JSONDecodeError, TypeError):
        return None


def find_existing_grant(client_id: str, audience: str) -> dict[str, Any] | None:
    result = run("auth0", "api", "get", "client-grants", check=False)
    if result.returncode != 0:
        return None
    try:
        data: dict[str, Any] | list[dict[str, Any]] = json.loads(result.stdout)
        grants: list[dict[str, Any]] = (
            data if isinstance(data, list) else data.get("client_grants", [])
        )
        return next(
            (
                g
                for g in grants
                if g.get("client_id") == client_id and g.get("audience") == audience
            ),
            None,
        )
    except (json.JSONDecodeError, TypeError):
        return None


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    check_auth0_cli()

    print("=" * 60)
    print("  Auth0 Setup")
    print("=" * 60)
    print("This will create all required Auth0 resources and write")
    print("the resulting values into your .env files.")
    print("Existing resources with matching names will be skipped.\n")

    # Tenant domain
    detected_tenant = detect_tenant()
    if not detected_tenant:
        print("(Could not detect active tenant from CLI — please enter it manually)")
    tenant_domain = prompt(
        "Auth0 tenant domain (e.g. myapp.eu.auth0.com)", default=detected_tenant
    )

    validate_tenant_login(tenant_domain)

    print()
    project_name = prompt("Project name", default="My Project")
    slug = project_name.lower().replace(" ", "-")

    base_domain = prompt("Base domain (e.g. dutyhub.dev or fabraham.dev)")
    domain_root = base_domain.split(".")[0]
    if domain_root == slug:
        default_api_id = f"https://api.{base_domain}"
    else:
        default_api_id = f"https://{slug}-api.{base_domain}"

    api_identifier = prompt("API identifier / audience URL", default=default_api_id)

    roles_namespace = prompt(
        "Roles namespace (domain used in token claims)",
        default=f"https://{base_domain}",
    )

    print("\nAdmin user to create:")
    admin_name = prompt("  Full name", default="Admin User")
    admin_email = prompt("  Email")
    admin_password = prompt("  Password", secret=True)

    print()
    print("Resources that will be created (or skipped if they already exist):")
    print(f"  Auth0 API (audience):  {api_identifier}")
    print(f"  SPA application:       {project_name} Web")
    print(f"  M2M application:       {project_name} Backend M2M")
    print("  Management API grant:  read:users, update:users, delete:users")
    print("  Role:                  admin")
    print(f"  Admin user:            {admin_email}")
    print("  Post-Login Action:     Add Roles to Access Token")

    confirm = input("\nProceed? [Y/n]: ").strip().lower()
    if confirm == "n":
        print("Aborted.")
        sys.exit(0)

    # ── Step 1: Create API ─────────────────────────────────────────────────────
    step(1, "Create Auth0 API")
    existing_api = find_existing_api(api_identifier)
    if existing_api:
        print(
            f"  Skipping — already exists: {existing_api.get('name')}  (id: {existing_api.get('id')})"
        )
    else:
        api_data = run_json(
            "auth0",
            "apis",
            "create",
            "--name",
            f"{project_name} API",
            "--identifier",
            api_identifier,
            "--signing-alg",
            "RS256",
            "--token-lifetime",
            "86400",
            "--scopes",
            "",
            "--no-input",
        )
        print(f"  Created API: {api_data.get('name')}  (id: {api_data.get('id')})")

    # ── Step 2: Create SPA application ────────────────────────────────────────
    step(2, "Create SPA Application")
    spa_name = f"{project_name} Web"
    existing_spa = find_existing_app(spa_name)
    if existing_spa:
        spa_client_id: str = existing_spa.get("client_id", "")
        print(f"  Skipping — already exists: {spa_name}  (client_id: {spa_client_id})")
    else:
        spa_data = run_json(
            "auth0",
            "apps",
            "create",
            "--name",
            spa_name,
            "--type",
            "spa",
            "--callbacks",
            "http://localhost:5173,http://localhost:5173/app/home",
            "--logout-urls",
            "http://localhost:5173",
            "--web-origins",
            "http://localhost:5173",
            "--no-input",
        )
        spa_client_id = spa_data.get("client_id", "")
        print(f"  Created SPA: {spa_data.get('name')}  (client_id: {spa_client_id})")

    # ── Step 3: Create M2M application ────────────────────────────────────────
    step(3, "Create M2M Application")
    m2m_name = f"{project_name} Backend M2M"
    existing_m2m = find_existing_app(m2m_name)
    if existing_m2m:
        m2m_client_id: str = existing_m2m.get("client_id", "")
        # Retrieve secret — list doesn't return it, so use show
        show_result = run(
            "auth0",
            "apps",
            "show",
            m2m_client_id,
            "--reveal-secrets",
            "--json",
            check=False,
        )
        try:
            show_data: dict[str, Any] = json.loads(show_result.stdout)
            m2m_client_secret: str = show_data.get("client_secret", "")
        except (json.JSONDecodeError, TypeError):
            m2m_client_secret = ""
        print(f"  Skipping — already exists: {m2m_name}  (client_id: {m2m_client_id})")
        if not m2m_client_secret:
            print(
                "  Warning: Could not retrieve client secret — copy it manually from the Auth0 Dashboard"
            )
    else:
        m2m_data = run_json(
            "auth0",
            "apps",
            "create",
            "--name",
            m2m_name,
            "--type",
            "m2m",
            "--reveal-secrets",
            "--no-input",
        )
        m2m_client_id = m2m_data.get("client_id", "")
        m2m_client_secret = m2m_data.get("client_secret", "")
        print(f"  Created M2M: {m2m_data.get('name')}  (client_id: {m2m_client_id})")

    # ── Step 4: Authorize M2M for Management API ───────────────────────────────
    step(4, "Authorize M2M app for Management API")
    mgmt_audience = f"https://{tenant_domain}/api/v2/"
    existing_grant = find_existing_grant(m2m_client_id, mgmt_audience)
    if existing_grant:
        print(f"  Skipping — grant already exists on {mgmt_audience}")
    else:
        grant_payload = json.dumps(
            {
                "client_id": m2m_client_id,
                "audience": mgmt_audience,
                "scope": ["read:users", "update:users", "delete:users"],
            }
        )
        run("auth0", "api", "post", "client-grants", "--data", grant_payload)
        print(f"  Granted read:users + update:users + delete:users on {mgmt_audience}")

    # ── Step 5: Create admin role ──────────────────────────────────────────────
    step(5, "Create admin role")
    existing_role = find_existing_role("admin")
    if existing_role:
        role_id: str | None = existing_role.get("id")
        print(f"  Skipping — already exists: role 'admin'  (id: {role_id})")
    else:
        run(
            "auth0",
            "roles",
            "create",
            "--name",
            "admin",
            "--description",
            "Administrator role with full access",
            "--no-input",
        )
        # Retrieve role ID via list (roles create doesn't reliably emit JSON)
        roles_result = run("auth0", "roles", "list", "--json", check=False)
        role_id = None
        try:
            roles: list[dict[str, Any]] = json.loads(roles_result.stdout)
            admin_role = next((r for r in roles if r.get("name") == "admin"), None)
            if admin_role:
                role_id = admin_role.get("id")
        except (json.JSONDecodeError, TypeError):
            pass
        print(f"  Created role 'admin'  (id: {role_id or 'unknown'})")

    # ── Step 6: Create admin user + assign role ────────────────────────────────
    step(6, "Create admin user")
    existing_user = find_existing_user(admin_email)
    if existing_user:
        user_id: str = existing_user.get("user_id", "")
        print(f"  Skipping — already exists: {admin_email}  (id: {user_id})")
    else:
        user_data = run_json(
            "auth0",
            "users",
            "create",
            "--name",
            admin_name,
            "--email",
            admin_email,
            "--password",
            admin_password,
            "--connection-name",
            "Username-Password-Authentication",
            "--no-input",
        )
        user_id = user_data.get("user_id", "")
        print(f"  Created user: {admin_email}  (id: {user_id})")

    if role_id and user_id:
        run("auth0", "users", "roles", "assign", user_id, "--roles", role_id)
        print(f"  Assigned 'admin' role to {admin_email}")
    else:
        print(
            "  Warning: Could not assign role automatically — do it manually in the dashboard"
        )

    # ── Step 7: Create + deploy Post-Login Action ──────────────────────────────
    step(7, "Create Post-Login Action (Add Roles to Access Token)")
    action_name = "Add Roles to Access Token"
    existing_action = find_existing_action(action_name)
    if existing_action:
        action_id: str | None = existing_action.get("id")
        print(f"  Skipping — already exists: '{action_name}'  (id: {action_id})")
    else:
        # Note: {{ and }} escape braces in Python f-strings → { and } in output
        action_code = (
            "exports.onExecutePostLogin = async (event, api) => {\n"
            f'    const namespace = "{roles_namespace}";\n'
            "    const roles = (event.authorization && event.authorization.roles) || [];\n"
            "    api.accessToken.setCustomClaim(`${namespace}/roles`, roles);\n"
            "};\n"
        )

        action_result = run(
            "auth0",
            "actions",
            "create",
            "--name",
            action_name,
            "--trigger",
            "post-login",
            "--code",
            action_code,
            "--no-input",
            check=False,
        )

        action_id = None
        try:
            action_data: dict[str, Any] = json.loads(action_result.stdout)
            action_id = action_data.get("id")
        except (json.JSONDecodeError, TypeError):
            pass

        if action_id:
            run("auth0", "actions", "deploy", action_id)
            print(f"  Created and deployed action  (id: {action_id})")
        else:
            print(
                "  Action created (could not auto-deploy — deploy manually in the dashboard)"
            )

    print()
    print("  ⚠  MANUAL STEP REQUIRED:")
    print("     Bind the action to the Login flow in the Auth0 Dashboard:")
    print("     Actions → Flows → Login → drag 'Add Roles to Access Token' in")

    # ── Step 8: Write env files ────────────────────────────────────────────────
    step(8, "Update environment files")

    update_env(
        ENV_FILE,
        {
            "AUTH0_DOMAIN": tenant_domain,
            "AUTH0_AUDIENCE": api_identifier,
            "AUTH0_CLIENT_ID": m2m_client_id,
            "AUTH0_CLIENT_SECRET": m2m_client_secret,
        },
    )

    update_env(
        FRONTEND_ENV_FILE,
        {
            "VITE_AUTH0_DOMAIN": tenant_domain,
            "VITE_AUTH0_CLIENT_ID": spa_client_id,
            "VITE_AUTH0_API_AUDIENCE": api_identifier,
            "VITE_AUTH0_CALLBACK_URL": "http://localhost:5173",
        },
    )

    # ── Summary ────────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  Setup complete!")
    print("=" * 60)
    print()
    print("Values written to .env and frontend/.env:")
    print(f"  AUTH0_DOMAIN           {tenant_domain}")
    print(f"  AUTH0_AUDIENCE         {api_identifier}")
    print(f"  AUTH0_CLIENT_ID        {m2m_client_id}")
    print(f"  VITE_AUTH0_CLIENT_ID   {spa_client_id}")
    print()
    print("Remaining manual steps:")
    print("  1. Bind 'Add Roles to Access Token' to the Login flow (see above)")
    print("  2. Restart your stack: just dev")


if __name__ == "__main__":
    main()
