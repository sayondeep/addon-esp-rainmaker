from flask import Flask, jsonify, request
import subprocess, os
import time

app = Flask(__name__)

def run_cli(cmd):
    result = subprocess.run(
        ["esp-rainmaker-cli"] + cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    return result.stdout.strip() or result.stderr.strip()

def ensure_login():
    """Ensure ESP RainMaker CLI is logged in"""
    # Check if already logged in
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
    profile = os.environ.get("ESP_RAINMAKER_PROFILE")

    # Default to global if profile is not set or is null
    if not profile or profile.lower() == "null" or profile.strip() == "":
        profile = "global"
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
print(f"  RAINMAKER_API_PORT: {os.environ.get('RAINMAKER_API_PORT', 'NOT SET')}")

login_success = ensure_login()
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

    # Apply same default logic as in ensure_login
    if not profile or profile.lower() == "null" or profile.strip() == "":
        profile = "global"

    return jsonify({
        "logged_in": is_logged_in,
        "email": os.environ.get("ESP_RAINMAKER_EMAIL", "Not set"),
        "profile": profile,
        "service": "ESP RainMaker API"
    })

if __name__ == "__main__":
    port = int(os.environ.get("RAINMAKER_API_PORT", "8099"))
    app.run(host="0.0.0.0", port=port)
