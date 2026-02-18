#!/usr/bin/env python3
"""
Auto-update Windsurf session parameters from IDE
This script dynamically updates .env with current IDE session info
"""

import re
import sqlite3
import subprocess
import sys
from pathlib import Path


def get_windsurf_session():
    """Extract current Windsurf IDE session info"""
    conn = None

    # Path to Windsurf state database
    state_db = (
        Path.home()
        / "Library"
        / "Application Support"
        / "Windsurf"
        / "User"
        / "globalStorage"
        / "state.vscdb"
    )

    if not state_db.exists():
        print("❌ Windsurf state database not found")
        return None

    try:
        conn = sqlite3.connect(str(state_db))
        cursor = conn.cursor()

        # Get API key
        cursor.execute("""
            SELECT value FROM ItemTable 
            WHERE key = 'codeium.accountInfo'
        """)
        result = cursor.fetchone()

        if not result:
            print("❌ No account info found")
            return None

        account_info = result[0]

        # Extract API key and install ID
        api_key_match = re.search(r'"apiKey":"(sk-ws-[^"]+)"', account_info)
        install_id_match = re.search(r'"installationId":"([^"]+)"', account_info)

        if not api_key_match or not install_id_match:
            print("❌ Could not extract API key or install ID")
            return None

        api_key = api_key_match.group(1)
        install_id = install_id_match.group(1)

        # Get current LS port and CSRF
        ls_port, ls_csrf = detect_language_server()

        session_info = {
            "api_key": api_key,
            "install_id": install_id,
            "ls_port": ls_port,
            "ls_csrf": ls_csrf,
        }

        print("✅ Extracted session info:")
        print(f"   API Key: {api_key[:20]}...")
        print(f"   Install ID: {install_id}")
        print(f"   LS Port: {ls_port}")
        print(f"   LS CSRF: {ls_csrf[:20]}...")

        return session_info

    except Exception as e:
        print(f"❌ Error extracting session info: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def detect_language_server():
    """Detect running Windsurf language server port and CSRF token"""

    try:
        # Find LS process
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)

        ls_port = 0
        ls_csrf = ""

        for line in result.stdout.splitlines():
            if "language_server_macos_arm" not in line or "grep" in line:
                continue

            # Extract CSRF token
            csrf_match = re.search(r"--csrf_token\s+(\S+)", line)
            if csrf_match:
                ls_csrf = csrf_match.group(1)

            # Get process ID
            pid = line.split()[1]

            # Find port for this PID
            try:
                lsof = subprocess.run(
                    ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", pid],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                for ll in lsof.stdout.splitlines():
                    port_match = re.search(r":(\d+)\s+\(LISTEN\)", ll)
                    if port_match:
                        ls_port = int(port_match.group(1))
                        break

            except Exception:
                pass

        return ls_port, ls_csrf

    except Exception as e:
        print(f"❌ Error detecting LS: {e}")
        return 0, ""


def update_env_file(session_info):
    """Update .env file with current session info"""

    from src.brain.config import PROJECT_ROOT
    env_file = PROJECT_ROOT / ".env"

    if not env_file.exists():
        print("❌ .env file not found")
        return False

    try:
        # Read current .env
        with open(env_file) as f:
            content = f.read()

        # Update values
        lines = content.split("\n")
        updated_lines = []

        for line in lines:
            if line.startswith("WINDSURF_API_KEY="):
                updated_lines.append(f"WINDSURF_API_KEY={session_info['api_key']}")
            elif line.startswith("WINDSURF_INSTALL_ID="):
                updated_lines.append(f"WINDSURF_INSTALL_ID={session_info['install_id']}")
            elif line.startswith("WINDSURF_LS_PORT="):
                updated_lines.append(f"WINDSURF_LS_PORT={session_info['ls_port']}")
            elif line.startswith("WINDSURF_LS_CSRF="):
                updated_lines.append(f"WINDSURF_LS_CSRF={session_info['ls_csrf']}")
            else:
                updated_lines.append(line)

        # Write updated .env
        with open(env_file, "w") as f:
            f.write("\n".join(updated_lines))

        print("✅ Updated .env file with current session")
        return True

    except Exception as e:
        print(f"❌ Error updating .env: {e}")
        return False


def main():
    print("🔄 Auto-updating Windsurf session parameters...")

    session_info = get_windsurf_session()

    if not session_info:
        print("❌ Failed to get session info")
        sys.exit(1)

    if session_info["ls_port"] == 0:
        print("❌ Language server not running")
        sys.exit(1)

    if update_env_file(session_info):
        print("✅ Session update completed successfully!")
    else:
        print("❌ Failed to update .env")
        sys.exit(1)


if __name__ == "__main__":
    main()
