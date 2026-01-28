from flask import Flask, jsonify, request
import subprocess, os
import time
import hashlib
import re

app = Flask(__name__)

def run_cli(cmd):
    result = subprocess.run(
        ["esp-rainmaker-cli"] + cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    return result.stdout.strip() or result.stderr.strip()

def get_custom_profiles():
    """Get list of custom profile names"""
    output = run_cli(["profile", "list"])
    custom_profiles = []

    print(f"DEBUG: Profile list output:\n{output}")

    lines = output.splitlines()
    current_profile = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Profile name is on a line starting with spaces and a name (may have "(current)" suffix)
        if re.match(r'^\s+\w+', line):
            # Extract profile name (first word after leading spaces, before any parentheses)
            match = re.match(r'^\s+(\w+)', line)
            if match:
                current_profile = match.group(1)
                print(f"DEBUG: Found profile name: {current_profile}")
        # Check if it's a custom profile - look for "Type: custom" in the same or following lines
        elif current_profile:
            if "Type: custom" in stripped:
                custom_profiles.append(current_profile)
                print(f"DEBUG: Added custom profile: {current_profile}")
                current_profile = None
            elif "Type: builtin" in stripped:
                print(f"DEBUG: Skipping builtin profile: {current_profile}")
                current_profile = None
            # Also check if we've moved to the next profile (new profile name line)
            elif re.match(r'^\s+\w+', line):
                # This shouldn't happen as we already handled it above, but just in case
                current_profile = None

    print(f"DEBUG: Found {len(custom_profiles)} custom profiles: {custom_profiles}")
    return custom_profiles

def remove_all_custom_profiles():
    """Remove all custom profiles"""
    custom_profiles = get_custom_profiles()
    for profile_name in custom_profiles:
        print(f"Removing custom profile: {profile_name}")
        result = subprocess.run(
            ["esp-rainmaker-cli", "profile", "remove", profile_name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if result.returncode == 0:
            print(f"Successfully removed profile: {profile_name}")
        else:
            print(f"Failed to remove profile {profile_name}: {result.stderr}")

def create_profile_from_base_url(profile_name, base_url):

    print(f"Creating new profile '{profile_name}' with base URL: {base_url}")

    # Create profile with the base_url using --base-url parameter
    result = subprocess.run(
        ["esp-rainmaker-cli", "profile", "add", profile_name, "--base-url", base_url],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    if result.returncode == 0:
        print(f"Successfully created profile: {profile_name}")
        return profile_name
    else:
        print(f"Failed to create profile: {result.stderr}")
        return None

def manage_profiles_if_needed():
    """Manage profiles if base_url is provided - runs before login check"""
    base_url = os.environ.get("ESP_RAINMAKER_BASE_URL")
    profile_name = os.environ.get("ESP_RAINMAKER_PROFILE")

    # If base_url is provided, manage profiles
    if base_url and base_url.strip() and base_url.lower() != "null":
        print(f"Base URL provided: {base_url}, managing profiles...")

        # Logout first to ensure fresh login with new profile
        print("Logging out from current session...")
        logout_result = subprocess.run(
            ["esp-rainmaker-cli", "logout"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if logout_result.returncode == 0:
            print("Successfully logged out")
        else:
            print(f"Note: Logout result (may not be logged in): {logout_result.stderr}")

        # Remove all custom profiles
        remove_all_custom_profiles()

        # Create new profile with base_url
        new_profile = create_profile_from_base_url(profile_name.strip(), base_url.strip())
        if new_profile:
            # Switch to the new profile so all subsequent commands use it
            print(f"Switching to profile: {new_profile}")
            switch_result = subprocess.run(
                ["esp-rainmaker-cli", "profile", "switch", new_profile],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if switch_result.returncode == 0:
                print(f"Successfully switched to profile: {new_profile}")
            else:
                print(f"WARNING: Failed to switch to profile {new_profile}: {switch_result.stderr}")

            # Update environment variable so ensure_login() will use this profile
            os.environ["ESP_RAINMAKER_PROFILE"] = new_profile
            print(f"Successfully created and will use profile: {new_profile}")
            return new_profile
        else:
            print("WARNING: Failed to create profile from base_url, will use configured profile")

    return None

def ensure_login(force_login=False):
    """Ensure ESP RainMaker CLI is logged in"""
    # Check if already logged in (unless forced)
    if not force_login:
        result = subprocess.run(
            ["esp-rainmaker-cli", "getnodes"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # If we get nodes or a proper response, we're logged in
        if result.returncode == 0 and not ("login" in result.stderr.lower() or "authentication" in result.stderr.lower()):
            return True

    # Need to login
    email = os.environ.get("ESP_RAINMAKER_EMAIL")
    password = os.environ.get("ESP_RAINMAKER_PASSWORD")

    # Determine which profile to use
    profile = os.environ.get("ESP_RAINMAKER_PROFILE")
    if not profile or profile.lower() == "null" or profile.strip() == "":
        profile = "my_profile"
        print(f"Profile not set or null, defaulting to: {profile}")

    if not email or not password:
        print("ERROR: ESP_RAINMAKER_EMAIL and ESP_RAINMAKER_PASSWORD must be set")
        return False

    print(f"Logging in to ESP RainMaker with email: {email}, profile: {profile}")

    # Attempt login with profile
    login_result = subprocess.run(
        ["esp-rainmaker-cli", "login", "--email", email, "--password", password, "--profile", profile],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    if login_result.returncode == 0:
        print("Successfully logged in to ESP RainMaker")
        return True
    else:
        print(f"Login failed: {login_result.stderr}")
        return False

# Ensure login on startup
print(f"DEBUG: Environment variables on startup:")
print(f"  ESP_RAINMAKER_EMAIL: {os.environ.get('ESP_RAINMAKER_EMAIL', 'NOT SET')}")
print(f"  ESP_RAINMAKER_PASSWORD: {'SET' if os.environ.get('ESP_RAINMAKER_PASSWORD') else 'NOT SET'}")
print(f"  ESP_RAINMAKER_PROFILE: {os.environ.get('ESP_RAINMAKER_PROFILE', 'NOT SET')}")
print(f"  ESP_RAINMAKER_BASE_URL: {os.environ.get('ESP_RAINMAKER_BASE_URL', 'NOT SET')}")
print(f"  RAINMAKER_API_PORT: {os.environ.get('RAINMAKER_API_PORT', 'NOT SET')}")

# Manage profiles on startup if base_url is provided
profile_created = manage_profiles_if_needed()

# Force login if a new profile was created (since we logged out)
# If profile was created, we already switched to it, so pass profile_already_switched=True
login_success = ensure_login(force_login=(profile_created is not None))
if not login_success:
    print("WARNING: Failed to login to ESP RainMaker. API endpoints may not work.")

@app.route("/getnodes", methods=["GET"])
def getnodes():
    # Ensure we're logged in before making API calls
    if not ensure_login():
        return jsonify({"error": "Authentication failed", "nodes": [], "count": 0})

    output = run_cli(["getnodes"])
    nodes = []

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip initialization messages and other non-node lines
        if ("Initialising" in line or "Success" in line or
            "Error" in line or "Failed" in line or
            line.startswith("ESP") or line.startswith("Note")):
            continue
        if ". " in line:
            try:
                _, node_id = line.split(". ", 1)
                node_id = node_id.strip()
                # Only add if it looks like a valid node ID (alphanumeric)
                if node_id and len(node_id) > 10 and node_id.replace('-', '').replace('_', '').isalnum():
                    nodes.append(node_id)
            except ValueError:
                continue

    return jsonify({"nodes": nodes, "count": len(nodes)})
@app.route("/nodedetails/<node_id>", methods=["GET"])
def nodedetails(node_id):
    # Ensure we're logged in before making API calls
    if not ensure_login():
        return jsonify({"error": "Authentication failed", "node_id": node_id, "details": None})

    output = run_cli(["getnodedetails", node_id, "--raw"])
    try:
        import json
        details = json.loads(output)
        return jsonify({"node_id": node_id, "details": details})
    except json.JSONDecodeError:
        return jsonify({"node_id": node_id, "details": output, "error": "Failed to parse JSON"})

@app.route("/getparams/<node_id>", methods=["GET"])
def getparams(node_id):
    """Get device parameters using efficient getparams command"""
    # Ensure we're logged in before making API calls
    if not ensure_login():
        return jsonify({"error": "Authentication failed", "node_id": node_id, "params": None})

    output = run_cli(["getparams", node_id])
    try:
        import json
        params = json.loads(output)
        return jsonify({"node_id": node_id, "params": params})
    except json.JSONDecodeError:
        return jsonify({"node_id": node_id, "params": output, "error": "Failed to parse JSON"})

@app.route("/setparams/<node_id>", methods=["POST"])
def setparams(node_id):
    """Set device parameters using setparams command"""
    # Ensure we're logged in before making API calls
    if not ensure_login():
        return jsonify({"error": "Authentication failed", "node_id": node_id, "success": False})

    try:
        # Get JSON data from request
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided", "node_id": node_id, "success": False})

        # Convert data to JSON string for CLI command
        import json
        data_str = json.dumps(data)

        # Execute setparams command
        output = run_cli(["setparams", "--data", data_str, node_id])

        # Check if command was successful (setparams usually returns empty on success)
        success = "error" not in output.lower() and "failed" not in output.lower()

        return jsonify({
            "node_id": node_id,
            "success": success,
            "output": output.strip(),
            "data_sent": data
        })

    except Exception as e:
        return jsonify({
            "error": str(e),
            "node_id": node_id,
            "success": False
        })

@app.route("/rainmakernodes", methods=["GET"])
def rainmakernodes():
    """Get RainMaker devices (includes traditional RainMaker and RainMaker Matter, excludes pure Matter)"""
    # Ensure we're logged in before making API calls
    if not ensure_login():
        return jsonify({"error": "Authentication failed", "count": 0, "devices": []})

    output = run_cli(["getnodes"])
    nodes = []
    all_devices = []

    # First get all nodes
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip initialization messages and other non-node lines
        if ("Initialising" in line or "Success" in line or
            "Error" in line or "Failed" in line or
            line.startswith("ESP") or line.startswith("Note")):
            continue
        if ". " in line:
            try:
                _, node_id = line.split(". ", 1)
                node_id = node_id.strip()
                # Only add if it looks like a valid node ID (alphanumeric)
                if node_id and len(node_id) > 10 and node_id.replace('-', '').replace('_', '').isalnum():
                    nodes.append(node_id)
            except ValueError:
                continue

    # Get details for all nodes and include only RainMaker devices (not pure Matter)
    for node_id in nodes:
        try:
            details_output = run_cli(["getnodedetails", node_id, "--raw"])
            import json
            details = json.loads(details_output)

            # Process each node detail
            node_details_list = details.get("node_details", [])
            for node_detail in node_details_list:
                node_type = node_detail.get("node_type")  # Can be None for traditional RainMaker

                # Skip ONLY pure Matter devices - include everything else
                if node_type == "pure_matter":
                    continue

                # Include:
                # 1. Traditional RainMaker devices (no node_type field)
                # 2. RainMaker Matter devices (node_type != "pure_matter")
                # 3. Any other RainMaker device types

                is_matter = node_detail.get("is_matter", False)
                connected = node_detail.get("status", {}).get("connectivity", {}).get("connected", False)

                device_name = f"RainMaker Device {node_id[:8]}"  # fallback name
                device_type = "RainMaker Device"

                # Try to get device name and type from different sources
                if is_matter and "metadata" in node_detail:
                    # Matter-enabled device (could be RainMaker or pure Matter)
                    metadata = node_detail.get("metadata", {})
                    matter_data = metadata.get("Matter", {})
                    is_rainmaker = matter_data.get("isRainmaker", False)

                    # For Matter devices, include if isRainmaker is true OR if node_type is not pure_matter
                    if is_rainmaker or node_type != "pure_matter":
                        device_name = matter_data.get("deviceName", device_name)
                        device_type = f"RainMaker Matter Device (Type: {matter_data.get('deviceType', 'unknown')})"
                    else:
                        continue  # Skip pure Matter devices with isRainmaker: false

                elif "config" in node_detail:
                    # Traditional RainMaker device (usually no node_type field)
                    config = node_detail.get("config", {})
                    info = config.get("info", {})
                    device_name = info.get("name", device_name)
                    device_type = info.get("type", "RainMaker Device")

                    # Add device parameters if available
                    params = node_detail.get("params", {})
                    if params:
                        device_type = f"RainMaker Device ({', '.join(params.keys())})"

                elif node_type and node_type != "pure_matter":
                    # Other RainMaker device types we might not recognize yet
                    device_name = f"RainMaker Device {node_id[:8]}"
                    device_type = f"RainMaker Device ({node_type})"
                else:
                    # Unknown structure and no config, skip
                    continue

                device_info = {
                    "node_id": node_id,
                    "name": device_name,
                    "type": device_type,
                    "node_type": node_type or "traditional_rainmaker",  # Show as traditional if no node_type
                    "is_matter": is_matter,
                    "connected": connected
                }

                all_devices.append(device_info)
                break  # Only process first node detail for now

        except (json.JSONDecodeError, Exception) as e:
            print(f"Error getting details for {node_id}: {e}")
            continue

    return jsonify({
        "count": len(all_devices),
        "devices": all_devices
    })

@app.route("/allnodes", methods=["GET"])
def allnodes():
    """Get all nodes with their device type (RainMaker vs Matter)"""
    # Ensure we're logged in before making API calls
    if not ensure_login():
        return jsonify({"error": "Authentication failed", "nodes": [], "count": 0, "node_details": []})

    output = run_cli(["getnodes"])
    nodes = []
    all_nodes = []

    # First get all nodes
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip initialization messages and other non-node lines
        if ("Initialising" in line or "Success" in line or
            "Error" in line or "Failed" in line or
            line.startswith("ESP") or line.startswith("Note")):
            continue
        if ". " in line:
            try:
                _, node_id = line.split(". ", 1)
                node_id = node_id.strip()
                # Only add if it looks like a valid node ID (alphanumeric)
                if node_id and len(node_id) > 10 and node_id.replace('-', '').replace('_', '').isalnum():
                    nodes.append(node_id)
            except ValueError:
                continue

    # Get details for all nodes
    for node_id in nodes:
        try:
            details_output = run_cli(["getnodedetails", node_id, "--raw"])
            import json
            details = json.loads(details_output)

            # Check device type
            node_details_list = details.get("node_details", [])
            device_type = "unknown"
            device_name = f"Node {node_id[:8]}"

            for node_detail in node_details_list:
                metadata = node_detail.get("metadata", {})
                matter_data = metadata.get("Matter", {})
                is_rainmaker = matter_data.get("isRainmaker", False)

                if is_rainmaker:
                    device_type = "rainmaker"
                else:
                    device_type = "matter"

                device_name = matter_data.get("deviceName", device_name)
                break

            all_nodes.append({
                "node_id": node_id,
                "device_type": device_type,
                "device_name": device_name,
                "details": details
            })

        except (json.JSONDecodeError, Exception) as e:
            print(f"Error getting details for {node_id}: {e}")
            continue

    return jsonify({"nodes": [node["node_id"] for node in all_nodes],
                   "count": len(all_nodes),
                   "node_details": all_nodes})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "ESP RainMaker API"})

@app.route("/login-status", methods=["GET"])
def login_status():
    """Check ESP RainMaker login status"""
    is_logged_in = ensure_login()
    profile = os.environ.get("ESP_RAINMAKER_PROFILE")
    base_url = os.environ.get("ESP_RAINMAKER_BASE_URL")

    # Apply same default logic as in ensure_login
    if base_url and base_url.strip() and base_url.lower() != "null":
        # If base_url is set, we'll use the created profile
        # Get the actual current profile from CLI
        result = subprocess.run(
            ["esp-rainmaker-cli", "profile", "current"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if result.returncode == 0:
            # Extract profile name from output
            for line in result.stdout.splitlines():
                if "Profile:" in line or "Name:" in line:
                    match = re.search(r'(?:Profile|Name):\s*(\w+)', line)
                    if match:
                        profile = match.group(1)
                        break
    elif not profile or profile.lower() == "null" or profile.strip() == "":
        profile = "my_profile"

    return jsonify({
        "logged_in": is_logged_in,
        "email": os.environ.get("ESP_RAINMAKER_EMAIL", "Not set"),
        "profile": profile,
        "base_url": base_url if base_url else "Not set",
        "service": "ESP RainMaker API"
    })

if __name__ == "__main__":
    port = int(os.environ.get("RAINMAKER_API_PORT", "8099"))
    app.run(host="0.0.0.0", port=port)
