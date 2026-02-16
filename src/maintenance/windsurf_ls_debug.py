import re
import subprocess


def debug_detect():
    print("--- DEBUG: _detect_language_server ---")
    try:
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            if "language_server_macos_arm" not in line or "grep" in line:
                continue

            print(f"FOUND LS PROCESS: {line}")

            csrf_token = ""
            m = re.search(r"--csrf_token\s+(\S+)", line)
            if m:
                csrf_token = m.group(1)
            print(f"CSRF TOKEN: {csrf_token}")

            parts = line.split()
            if len(parts) >= 2:
                pid = parts[1]
                print(f"PID: {pid}")
                try:
                    # Check if lsof exists
                    import shutil

                    lsof_path = shutil.which("lsof")
                    print(f"LSOF PATH: {lsof_path}")

                    cmd = ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", pid]
                    print(f"RUNNING: {' '.join(cmd)}")
                    lsof = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    print(f"LSOF OUTPUT:\n{lsof.stdout}")
                    print(f"LSOF ERR:\n{lsof.stderr}")

                    port = 0
                    for ll in lsof.stdout.splitlines():
                        if "LISTEN" in ll:
                            m2 = re.search(r":(\d+)\s+\(LISTEN\)", ll)
                            if m2:
                                candidate = int(m2.group(1))
                                if port == 0 or candidate < port:
                                    port = candidate
                    print(f"DETECTED PORT: {port}")

                    if port and csrf_token:
                        print("--- TESTING HEARTBEAT ---")
                        import requests

                        try:
                            r = requests.post(
                                f"http://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/Heartbeat",
                                headers={
                                    "Content-Type": "application/json",
                                    "x-codeium-csrf-token": csrf_token,
                                },
                                json={},
                                timeout=3,
                            )
                            print(f"HEARTBEAT STATUS: {r.status_code}")
                            print(f"HEARTBEAT RESPONSE: {r.text}")
                            if r.status_code == 200:
                                print("✅ HEARTBEAT SUCCESSFUL")
                                return True
                            print("❌ HEARTBEAT FAILED (Non-200)")
                        except Exception as e:
                            print(f"❌ HEARTBEAT FAILED (Error): {e}")

                        return False
                except Exception as e:
                    print(f"❌ LSOF FAILED: {e}")
            break
    except Exception as e:
        print(f"❌ PS FAILED: {e}")
    return False


if __name__ == "__main__":
    debug_detect()
