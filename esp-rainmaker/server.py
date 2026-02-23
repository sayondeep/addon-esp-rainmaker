import asyncio
import websockets
import os
import sys
import json
from pathlib import Path

# Add esp-rainmaker-cli to path to import rmaker_lib
# Prioritize local source code folder over installed package
rmaker_lib_found = False

# Strategy 1: Try local source code directory (same directory as server.py)
possible_paths = [
    os.path.join(os.path.dirname(__file__), "esp-rainmaker-cli"),  # Same directory as server.py
]

for path in possible_paths:
    abs_path = os.path.abspath(path)
    if os.path.exists(abs_path) and os.path.exists(os.path.join(abs_path, "rmaker_lib")):
        # Insert at the beginning of sys.path to prioritize over installed packages
        sys.path.insert(0, abs_path)
        rmaker_lib_found = True
        print(f"Using esp-rainmaker-cli from: {abs_path}")
        break

# Strategy 2: Fall back to installed package if local source not found
if not rmaker_lib_found:
    try:
        import rmaker_lib
        rmaker_lib_found = True
        print("Using esp-rainmaker-cli from installed package")
    except ImportError:
        pass

if not rmaker_lib_found:
    raise ImportError(
        "Could not find rmaker_lib. Please ensure esp-rainmaker-cli source code is available "
        "in the same directory as server.py (esp-rainmaker-cli/) or install the package."
    )

# Import ESP RainMaker library
from rmaker_lib import session, node, user, configmanager
from rmaker_lib.exceptions import (
    HttpErrorResponse,
    NetworkError,
    InvalidConfigError,
    SSLError,
    RequestTimeoutError,
    AuthenticationError,
    ExpiredSessionError
)

# Global session and config objects
_global_session = None
_global_config = None
_global_node_cache = None
_global_session_store = None

def get_config(profile_override=None):
    """Get or create a Config object"""
    global _global_config
    if _global_config is None or profile_override:
        _global_config = configmanager.Config(profile_override=profile_override)
    return _global_config

def get_session(profile_override=None, force_refresh=False):
    """Get or create a Session object, refreshing if needed"""
    global _global_session
    config = get_config(profile_override)

    if force_refresh or _global_session is None:
        try:
            _global_session = session.Session(profile_override=profile_override)
        except (InvalidConfigError, ExpiredSessionError):
            _global_session = None
            raise

    return _global_session

def get_cache_objects(profile_override=None):
    """Get or create NodeCache and SessionStore objects for local control"""
    global _global_node_cache, _global_session_store
    from rmaker_lib.node_cache import NodeCache, is_cache_enabled, _get_cache_base_dir
    from rmaker_lib.session_store import SessionStore

    config = get_config(profile_override)
    profile_name = config.get_current_profile_name()
    profile_config = config.get_profile_config_for_current()

    # Always enable cache for session reuse (critical for performance)
    cache_enabled = is_cache_enabled(profile_config, no_cache_flag=False)
    if not cache_enabled:
        try:
            config.profile_manager.set_cache_enabled(profile_name, True)
            profile_config = config.get_profile_config_for_current()
            cache_enabled = True
        except Exception as e:
            print(f"Note: Could not auto-enable cache: {e}")

    try:
        user_id = config.get_user_id()
    except:
        user_id = 'unknown'

    base_dir = _get_cache_base_dir(profile_config)
    cache_dir = os.path.join(base_dir, profile_name, user_id or 'unknown')

    if _global_node_cache is None or _global_session_store is None:
        _global_node_cache = NodeCache(profile_name, user_id, enabled=True)
        _global_session_store = SessionStore(cache_dir, enabled=True)

    return _global_node_cache, _global_session_store

def auto_resolve_pop(node_obj, node_cache=None):
    """Auto-resolve POP from cache or cloud for a node"""
    node_id = node_obj.get_nodeid()
    pop = None

    # Try to get POP from cache first (fast!)
    if node_cache:
        try:
            from rmaker_lib.node_cache import extract_local_control_info
            lc_info = node_cache.get_local_control_info(node_id)
            if lc_info and lc_info.get('pop'):
                pop = lc_info.get('pop')
                return pop
        except Exception as e:
            pass

    # If not in cache, try to fetch from cloud
    if not pop:
        try:
            cloud_params = node_obj.get_node_params()
            if cloud_params:
                from rmaker_lib.node_cache import extract_local_control_info
                lc_info = extract_local_control_info(cloud_params)
                if lc_info and lc_info.get('pop'):
                    pop = lc_info.get('pop')
                    # Cache it for future use
                    if node_cache:
                        try:
                            node_cache.set_local_control_info(node_id, lc_info)
                        except:
                            pass
                    return pop
        except Exception as e:
            pass

    return None

def get_node_params_with_auto(node_obj, sess):
    """Get node parameters using --auto (local first, fallback to cloud)"""
    node_id = node_obj.get_nodeid()
    node_cache, session_store = get_cache_objects()

    # Auto-resolve POP
    pop = auto_resolve_pop(node_obj, node_cache)

    # Try local control first if we have POP
    if pop:
        try:
            from rmaker_lib.local_control import run_local_control_operation
            result = run_local_control_operation(
                node_id,
                'get_params',
                pop=pop,
                transport='http',
                port=8080,
                sec_ver=1,
                node_cache=node_cache,
                session_store=session_store
            )
            if result:
                return result
        except Exception as e:
            # Local control failed, fall back to cloud
            pass

    # Fall back to cloud API
    return node_obj.get_node_params()

def set_node_params_with_auto(node_obj, data, sess):
    """Set node parameters using --auto (local first, fallback to cloud)"""
    node_id = node_obj.get_nodeid()
    node_cache, session_store = get_cache_objects()

    # Auto-resolve POP
    pop = auto_resolve_pop(node_obj, node_cache)

    # Try local control first if we have POP
    if pop:
        try:
            from rmaker_lib.local_control import run_local_control_operation
            result = run_local_control_operation(
                node_id,
                'set_params',
                data=data,
                pop=pop,
                transport='http',
                port=8080,
                sec_ver=1,
                node_cache=node_cache,
                session_store=session_store
            )
            if result:
                return True
        except Exception as e:
            # Local control failed, fall back to cloud
            pass

    # Fall back to cloud API
    return node_obj.set_node_params(data)

def get_custom_profiles():
    """Get list of custom profile names"""
    config = get_config()
    all_profiles = config.profile_manager.list_profiles()
    custom_profiles = []

    for profile_name, profile_config in all_profiles.items():
        # Custom profiles have builtin: False or are in custom_profiles
        if not profile_config.get('builtin', True):
            custom_profiles.append(profile_name)

    print(f"DEBUG: Found {len(custom_profiles)} custom profiles: {custom_profiles}")
    return custom_profiles

def remove_all_custom_profiles():
    """Remove all custom profiles"""
    custom_profiles = get_custom_profiles()
    config = get_config()

    for profile_name in custom_profiles:
        print(f"Removing custom profile: {profile_name}")
        try:
            config.profile_manager.delete_custom_profile(profile_name)
            print(f"Successfully removed profile: {profile_name}")
        except Exception as e:
            print(f"Failed to remove profile {profile_name}: {e}")

def create_profile_from_base_url(profile_name, base_url):
    """Create a new profile with the given base URL"""
    print(f"Creating new profile '{profile_name}' with base URL: {base_url}")
    config = get_config()

    try:
        config.profile_manager.create_custom_profile(
            profile_name=profile_name,
            base_url=base_url,
            description=f"Custom profile created from base URL: {base_url}",
            cache_enabled=False
        )
        print(f"Successfully created profile: {profile_name}")
        return profile_name
    except Exception as e:
        print(f"Failed to create profile: {e}")
        return None

def manage_profiles_if_needed():
    """Manage profiles if base_url is provided - runs before login check"""
    base_url = os.environ.get("ESP_RAINMAKER_BASE_URL")
    profile_name = os.environ.get("ESP_RAINMAKER_PROFILE")

    # If base_url is provided, manage profiles
    if base_url and base_url.strip() and base_url.lower() != "null":
        print(f"Base URL provided: {base_url}, managing profiles...")
        config = get_config()

        # Logout first to ensure fresh login with new profile
        print("Logging out from current session...")
        try:
            current_profile = config.profile_manager.get_current_profile()
            config.remove_curr_login_creds()
            print("Successfully logged out")
        except Exception as e:
            print(f"Note: Logout result (may not be logged in): {e}")

        # Remove all custom profiles
        remove_all_custom_profiles()

        # Create new profile with base_url
        new_profile = create_profile_from_base_url(profile_name.strip(), base_url.strip())
        if new_profile:
            # Switch to the new profile
            print(f"Switching to profile: {new_profile}")
            try:
                config.profile_manager.set_current_profile(new_profile)
                print(f"Successfully switched to profile: {new_profile}")
            except Exception as e:
                print(f"WARNING: Failed to switch to profile {new_profile}: {e}")

            # Update environment variable
            os.environ["ESP_RAINMAKER_PROFILE"] = new_profile
            print(f"Successfully created and will use profile: {new_profile}")
            return new_profile
        else:
            print("WARNING: Failed to create profile from base_url, will use configured profile")

    return None

def ensure_login(force_login=False):
    """Ensure ESP RainMaker is logged in"""
    global _global_session

    # Check if already logged in (unless forced)
    if not force_login:
        try:
            sess = get_session()
            # Try to get nodes to verify session is valid
            sess.get_nodes()
            return True
        except (InvalidConfigError, ExpiredSessionError, HttpErrorResponse):
            # Session invalid or expired, need to login
            _global_session = None
        except Exception:
            # Other error, try to login anyway
            _global_session = None

    # Need to login
    email = os.environ.get("ESP_RAINMAKER_EMAIL")
    password = os.environ.get("ESP_RAINMAKER_PASSWORD")

    # Determine which profile to use
    profile = os.environ.get("ESP_RAINMAKER_PROFILE")
    if not profile or profile.lower() == "null" or profile.strip() == "":
        # Get current profile from config manager, default to "global"
        try:
            temp_config = get_config()
            profile = temp_config.profile_manager.get_current_profile()
            if not profile:
                profile = "global"
        except Exception:
            profile = "global"
        print(f"Profile not set or null, defaulting to: {profile}")

    if not email or not password:
        print("ERROR: ESP_RAINMAKER_EMAIL and ESP_RAINMAKER_PASSWORD must be set")
        return False

    print(f"Logging in to ESP RainMaker with email: {email}, profile: {profile}")

    try:
        # Check if profile exists before trying to use it
        temp_config = get_config()
        if not temp_config.profile_manager.profile_exists(profile):
            print(f"ERROR: Profile '{profile}' does not exist. Available profiles: {list(temp_config.profile_manager.list_profiles().keys())}")
            return False

        config = get_config(profile_override=profile)
        user_obj = user.User(email, config)
        sess = user_obj.login(password)
        _global_session = sess
        print("Successfully logged in to ESP RainMaker")
        return True
    except ValueError as e:
        # Profile doesn't exist
        print(f"Login failed: {e}")
        return False
    except NetworkError as e:
        print(f"Login failed: Network error - Could not connect to ESP RainMaker server.")
        print(f"Please check your Internet connection and verify the base URL for profile '{profile}' is correct.")
        return False
    except AuthenticationError as e:
        print(f"Login failed: Authentication error - {e}")
        return False
    except Exception as e:
        print(f"Login failed: {e}")
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
login_success = ensure_login(force_login=(profile_created is not None))
if not login_success:
    print("WARNING: Failed to login to ESP RainMaker. API endpoints may not work.")

# WebSocket message handlers
async def handle_getnodes():
    """Get list of all node IDs"""
    if not ensure_login():
        return {"error": "Authentication failed", "nodes": [], "count": 0}

    try:
        sess = get_session()
        # Run synchronous call in executor to avoid blocking event loop
        nodes_dict = await asyncio.to_thread(sess.get_nodes)
        nodes = list(nodes_dict.keys())
        return {"nodes": nodes, "count": len(nodes)}
    except Exception as e:
        print(f"Error getting nodes: {e}")
        return {"error": str(e), "nodes": [], "count": 0}

async def handle_nodedetails(node_id):
    """Get detailed information for a specific node"""
    if not ensure_login():
        return {"error": "Authentication failed", "node_id": node_id, "details": None}

    try:
        sess = get_session()
        # Run synchronous call in executor to avoid blocking event loop
        details = await asyncio.to_thread(sess.get_node_details_by_id, node_id)
        return {"node_id": node_id, "details": details}
    except Exception as e:
        print(f"Error getting node details for {node_id}: {e}")
        return {"error": str(e), "node_id": node_id, "details": None}

async def handle_getparams(node_id):
    """Get device parameters using --auto (local first, fallback to cloud)"""
    if not ensure_login():
        return {"error": "Authentication failed", "node_id": node_id, "params": None}

    try:
        sess = get_session()
        node_obj = node.Node(node_id, sess)
        # Run synchronous call in executor to avoid blocking event loop
        params = await asyncio.to_thread(get_node_params_with_auto, node_obj, sess)
        return {"node_id": node_id, "params": params}
    except Exception as e:
        print(f"Error getting params for {node_id}: {e}")
        return {"error": str(e), "node_id": node_id, "params": None}

async def handle_setparams(node_id, data):
    """Set device parameters using --auto (local first, fallback to cloud)"""
    if not ensure_login():
        return {"error": "Authentication failed", "node_id": node_id, "success": False}

    try:
        if not data:
            return {"error": "No data provided", "node_id": node_id, "success": False}

        sess = get_session()
        node_obj = node.Node(node_id, sess)
        # Run synchronous call in executor to avoid blocking event loop
        result = await asyncio.to_thread(set_node_params_with_auto, node_obj, data, sess)

        return {
            "node_id": node_id,
            "success": result is True,
            "data_sent": data
        }
    except Exception as e:
        print(f"Error setting params for {node_id}: {e}")
        return {
            "error": str(e),
            "node_id": node_id,
            "success": False
        }

async def handle_rainmakernodes():
    """Get RainMaker devices (includes traditional RainMaker and RainMaker Matter, excludes pure Matter)"""
    if not ensure_login():
        return {"error": "Authentication failed", "count": 0, "devices": []}

    try:
        sess = get_session()
        # Run synchronous call in executor to avoid blocking event loop
        all_node_details = await asyncio.to_thread(sess.get_node_details)
        node_details_list = all_node_details.get("node_details", [])

        all_devices = []

        for node_detail in node_details_list:
            node_id = node_detail.get("node_id")
            if not node_id:
                continue

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

        return {
            "count": len(all_devices),
            "devices": all_devices
        }
    except Exception as e:
        print(f"Error getting RainMaker nodes: {e}")
        return {"error": str(e), "count": 0, "devices": []}

async def handle_allnodes():
    """Get all nodes with their device type (RainMaker vs Matter)"""
    if not ensure_login():
        return {"error": "Authentication failed", "nodes": [], "count": 0, "node_details": []}

    try:
        sess = get_session()
        # Run synchronous call in executor to avoid blocking event loop
        all_node_details = await asyncio.to_thread(sess.get_node_details)
        node_details_list = all_node_details.get("node_details", [])

        all_nodes = []

        for node_detail in node_details_list:
            node_id = node_detail.get("node_id")
            if not node_id:
                continue

            device_type = "unknown"
            device_name = f"Node {node_id[:8]}"

            metadata = node_detail.get("metadata", {})
            matter_data = metadata.get("Matter", {})
            is_rainmaker = matter_data.get("isRainmaker", False)

            if is_rainmaker:
                device_type = "rainmaker"
            else:
                device_type = "matter"

            device_name = matter_data.get("deviceName", device_name)

            all_nodes.append({
                "node_id": node_id,
                "device_type": device_type,
                "device_name": device_name,
                "details": node_detail
            })

        return {
            "nodes": [node["node_id"] for node in all_nodes],
            "count": len(all_nodes),
            "node_details": all_nodes
        }
    except Exception as e:
        print(f"Error getting all nodes: {e}")
        return {"error": str(e), "nodes": [], "count": 0, "node_details": []}

async def handle_health():
    return {"status": "ok", "service": "ESP RainMaker API"}

async def handle_login_status():
    """Check ESP RainMaker login status"""
    is_logged_in = ensure_login()
    profile = os.environ.get("ESP_RAINMAKER_PROFILE")
    base_url = os.environ.get("ESP_RAINMAKER_BASE_URL")

    # Get the actual current profile
    try:
        config = get_config()
        current_profile = config.profile_manager.get_current_profile()
        if base_url and base_url.strip() and base_url.lower() != "null":
            profile = current_profile
        elif not profile or profile.lower() == "null" or profile.strip() == "":
            profile = current_profile if current_profile else "my_profile"
    except Exception:
        if not profile or profile.lower() == "null" or profile.strip() == "":
            profile = "my_profile"

    return {
        "logged_in": is_logged_in,
        "email": os.environ.get("ESP_RAINMAKER_EMAIL", "Not set"),
        "profile": profile,
        "base_url": base_url if base_url else "Not set",
        "service": "ESP RainMaker API"
    }

async def handle_message(websocket, message):
    """Handle incoming WebSocket message"""
    try:
        data = json.loads(message)
        msg_type = data.get("type")
        msg_id = data.get("id")
        payload = data.get("payload", {})

        response = None

        # Route message to appropriate handler
        if msg_type == "getnodes":
            response = await handle_getnodes()
        elif msg_type == "nodedetails":
            node_id = payload.get("node_id")
            if not node_id:
                response = {"error": "node_id required"}
            else:
                response = await handle_nodedetails(node_id)
        elif msg_type == "getparams":
            node_id = payload.get("node_id")
            if not node_id:
                response = {"error": "node_id required"}
            else:
                response = await handle_getparams(node_id)
        elif msg_type == "setparams":
            node_id = payload.get("node_id")
            data = payload.get("data")
            if not node_id:
                response = {"error": "node_id required"}
            elif data is None:
                response = {"error": "data required"}
            else:
                response = await handle_setparams(node_id, data)
        elif msg_type == "rainmakernodes":
            response = await handle_rainmakernodes()
        elif msg_type == "allnodes":
            response = await handle_allnodes()
        elif msg_type == "health":
            response = await handle_health()
        elif msg_type == "login_status":
            response = await handle_login_status()
        else:
            response = {"error": f"Unknown message type: {msg_type}"}

        # Send response
        response_message = {
            "id": msg_id,
            "type": msg_type,
            "payload": response
        }
        await websocket.send(json.dumps(response_message))

    except json.JSONDecodeError as e:
        error_response = {
            "id": None,
            "type": "error",
            "payload": {"error": f"Invalid JSON: {str(e)}"}
        }
        await websocket.send(json.dumps(error_response))
    except Exception as e:
        print(f"Error handling message: {e}")
        error_response = {
            "id": data.get("id") if 'data' in locals() else None,
            "type": data.get("type", "error") if 'data' in locals() else "error",
            "payload": {"error": str(e)}
        }
        await websocket.send(json.dumps(error_response))

async def websocket_handler(websocket, path):
    """Main WebSocket connection handler"""
    print(f"WebSocket client connected: {websocket.remote_address}")
    try:
        async for message in websocket:
            await handle_message(websocket, message)
    except websockets.exceptions.ConnectionClosed:
        print(f"WebSocket client disconnected: {websocket.remote_address}")
    except Exception as e:
        print(f"WebSocket error: {e}")

async def main():
    """Start WebSocket server"""
    port = int(os.environ.get("RAINMAKER_API_PORT", "8099"))
    host = "0.0.0.0"

    print(f"Starting ESP RainMaker WebSocket server on {host}:{port}")

    async with websockets.serve(websocket_handler, host, port):
        print(f"ESP RainMaker WebSocket server running on ws://{host}:{port}")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
