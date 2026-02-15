#!/usr/bin/env python3
import os
import re
import subprocess
import sys

# Configuration
LOG_DIR = "/Users/dev/.config/atlastrinity/logs/mikrotik"
MAX_SIZE = 1 * 1024 * 1024  # 1MB per file
STATE_FILE = os.path.join(LOG_DIR, ".last_id")
SSH_CMD = ["ssh", "-p", "666", "-o", "StrictHostKeyChecking=no", "admin@192.168.88.1"]


def get_last_id():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return f.read().strip()
        except:
            return None
    return None


def set_last_id(last_id):
    with open(STATE_FILE, "w") as f:
        f.write(last_id)


def get_active_log_file():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)

    i = 0
    while True:
        file_path = os.path.join(LOG_DIR, f"mikrotik_{i}.log")
        if not os.path.exists(file_path):
            return file_path
        if os.path.getsize(file_path) < MAX_SIZE:
            return file_path
        i += 1


def fetch_logs(last_id=None):
    cmd = [*SSH_CMD, "/log print detail show-ids without-paging"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"Error fetching logs: {result.stderr}")
            return []

        lines = result.stdout.splitlines()
        logs = []
        current_log = None

        # Parse logs into entries
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Match ID lines like *12F
            match = re.match(r"^\*([0-9A-F]+)$", line)
            if match:
                if current_log:
                    logs.append(current_log)
                current_log = {"id": match.group(1), "content": [line]}
            elif current_log:
                current_log["content"].append(line)

        if current_log:
            logs.append(current_log)

        if not logs:
            return []

        # If no last_id, return all logs
        if not last_id:
            return logs

        # Find logs newer than last_id
        new_logs = []
        found_last = False
        for log in logs:
            if found_last:
                new_logs.append(log)
            if log["id"] == last_id:
                found_last = True

        # If last_id was not found (maybe buffer rolled over), return all
        if not found_last:
            return logs

        return new_logs

    except Exception as e:
        print(f"Exception during fetch: {e}")
        return []


def main():
    try:
        last_id = get_last_id()
        new_logs = fetch_logs(last_id)

        if not new_logs:
            print("No new log entries.")
            return

        target_file = get_active_log_file()

        with open(target_file, "a") as f:
            f.writelines(
                "\n".join(log["content"]) + "\n\n" for log in new_logs
            )  # Double newline for readability

        set_last_id(new_logs[-1]["id"])
        print(f"Success: Saved {len(new_logs)} new entries to {target_file}")

    except Exception as e:
        print(f"Critical error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
