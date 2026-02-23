#!/usr/bin/env python3
"""
ESP RainMaker Device Control Example

This example demonstrates how to control ESP RainMaker devices using the
esp-rainmaker-cli library. It shows how to:
- Initialize a session
- List available nodes
- Get node parameters
- Set node parameters
- Use local control for faster operations

Usage:
    python3 examples/control_device.py [--node-id NODE_ID] [--local] [--pop POP_VALUE]

Requirements:
    - You must be logged in to ESP RainMaker CLI:
      esp-rainmaker-cli login
    - The device must be claimed and associated with your account
"""

import sys
import json
import argparse
import os
from pathlib import Path

# Add parent directory to path to import rmaker_lib
sys.path.insert(0, str(Path(__file__).parent.parent))

from rmaker_lib import session, node
from rmaker_lib.exceptions import (
    HttpErrorResponse,
    NetworkError,
    InvalidConfigError,
    SSLError,
    RequestTimeoutError
)
from rmaker_lib.logger import log


def auto_resolve_pop(node_obj, node_cache=None, silent=False):
    """
    Auto-resolve POP from cache or cloud for a node.
    Similar to _build_local_options_with_cache in rmaker_cmd/node.py

    :param node_obj: Node object
    :param node_cache: Optional NodeCache object
    :param silent: If True, don't print messages (for repeated calls)
    :return: POP string or None
    """
    node_id = node_obj.get_nodeid()
    pop = None

    # Try to get POP from cache first (fast!)
    if node_cache:
        try:
            lc_info = node_cache.get_local_control_info(node_id)
            if lc_info and lc_info.get('pop'):
                pop = lc_info.get('pop')
                if not silent:
                    log.debug(f"Using cached POP for node {node_id}")
                return pop
        except Exception as e:
            log.debug(f"Failed to get POP from cache: {e}")

    # If not in cache, try to fetch from cloud (only once)
    if not pop:
        try:
            if not silent:
                print("   🔍 Auto-resolving POP from cloud...")
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
                    if not silent:
                        print(f"   ✅ Resolved POP from cloud (cached for next time)")
                    return pop
        except Exception as e:
            log.debug(f"Failed to auto-resolve POP from cloud: {e}")

    return None


def refresh_session_token(sess):
    """
    Attempt to refresh the session token if it's expired.

    :param sess: Session object
    :return: True if token was refreshed or is valid, False otherwise
    """
    try:
        # This will automatically refresh if expired
        token = sess.config.get_access_token()
        if token:
            # Update the session's request header with the new token
            sess.id_token = token
            sess.request_header = {'Content-Type': 'application/json',
                                  'Authorization': token}
            return True
    except Exception as e:
        log.debug(f"Token refresh failed: {e}")
        return False
    return False


def diagnose_session(sess, profile_name=None):
    """
    Diagnose session issues and provide helpful information.

    :param sess: Session object
    :param profile_name: Optional profile name
    """
    print("\n🔍 Diagnosing session...")
    try:
        profile = sess.config.get_current_profile_name()
        print(f"   Profile: {profile}")
        print(f"   Region: {sess.config.get_region()}")

        # Check if tokens exist
        has_tokens = sess.config.profile_manager.has_profile_tokens(profile)
        print(f"   Has tokens: {has_tokens}")

        # Check built-in profiles only
        print("\n   Checking built-in profiles:")
        for prof in ['global', 'china']:
            try:
                has_tokens_prof = sess.config.profile_manager.has_profile_tokens(prof)
                status = "✅ Has tokens" if has_tokens_prof else "❌ No tokens"
                marker = " (current)" if prof == profile else ""
                print(f"      {prof}{marker}: {status}")
            except:
                print(f"      {prof}: Could not check")

        if has_tokens:
            try:
                # Try to get username
                username = sess.config.get_user_name()
                print(f"\n   Username: {username}")
            except:
                print("\n   Username: Could not retrieve")

            try:
                # Check token validity
                token = sess.config.get_access_token()
                if token:
                    print("   Token: Valid")
                else:
                    print("   Token: Invalid or expired")
            except Exception as e:
                print(f"   Token: Error - {e}")
        else:
            print("\n   ⚠️  No tokens found for this profile")
            print("\n   💡 Please login:")
            if profile_name:
                print(f"      esp-rainmaker-cli login --profile {profile_name}")
            else:
                print("      esp-rainmaker-cli login")
    except Exception as e:
        print(f"   ❌ Error during diagnosis: {e}")


def test_token(sess):
    """
    Test if the token works by making a simple API call.

    :param sess: Session object
    :return: True if token works, False otherwise
    """
    try:
        # Try to get nodes list (simpler API call)
        nodes = sess.get_nodes()
        return True, None
    except HttpErrorResponse as e:
        return False, e
    except Exception as e:
        return False, e


def list_nodes(sess, profile_name=None):
    """
    List all nodes associated with the current user.

    :param sess: Session object
    :param profile_name: Optional profile name for error messages
    :return: List of node info dictionaries
    """
    print("\n📋 Fetching your nodes...")
    try:
        # Ensure token is fresh and session header is updated
        try:
            fresh_token = sess.config.get_access_token()
            if fresh_token:
                # Update session header with fresh token
                sess.id_token = fresh_token
                sess.request_header = {'Content-Type': 'application/json',
                                      'Authorization': fresh_token}
                print("   ✅ Using fresh access token")
        except Exception as token_err:
            print(f"   ⚠️  Could not get fresh token: {token_err}")

        # Test token with a simpler API call first
        print("   🔍 Testing token with simple API call...")
        token_works, test_error = test_token(sess)
        if not token_works:
            if isinstance(test_error, HttpErrorResponse):
                error_str = str(test_error).lower()
                if 'unauthorized' in error_str:
                    print("   ❌ Token test failed: Unauthorized")
                    print(f"   Error: {test_error}")
                    print("\n   💡 The token appears to be invalid or expired.")
                    print("      Solutions:")
                    current_profile = sess.config.get_current_profile_name()
                    if current_profile == 'global':
                        print("      • Login again:")
                        print("        esp-rainmaker-cli login")
                    elif current_profile == 'china':
                        print("      • Login again:")
                        print("        esp-rainmaker-cli login --profile china")
                    else:
                        print("      • Try using global profile:")
                        print("        python3 examples/control_device.py --profile global")
                        print("      • Or login to global profile:")
                        print("        esp-rainmaker-cli login")
                    return []
                else:
                    print(f"   ⚠️  Token test failed: {test_error}")
            else:
                print(f"   ⚠️  Token test failed: {test_error}")
        else:
            print("   ✅ Token test passed")

        node_details = sess.get_node_details()

        if not node_details or 'node_details' not in node_details:
            print("   No nodes found. Please claim a device first.")
            return []

        nodes = node_details['node_details']
        if len(nodes) == 0:
            print("   No nodes found. Please claim a device first.")
            return []

        print(f"   Found {len(nodes)} node(s):")
        for idx, node_info in enumerate(nodes, 1):
            node_id = node_info.get('id', 'Unknown')
            config = node_info.get('config', {})
            info = config.get('info', {})
            node_name = info.get('name', 'Unnamed')
            print(f"   {idx}. {node_name} (ID: {node_id})")

        return nodes
    except HttpErrorResponse as e:
        error_str = str(e).lower()
        # Check error response directly for unauthorized errors
        is_auth_error = False
        error_details = {}
        try:
            err_resp = e.err_resp
            error_code = str(err_resp.get('error_code', '')).lower()
            description = str(err_resp.get('description', '')).lower()
            message = str(err_resp.get('message', '')).lower()
            status = str(err_resp.get('status', '')).lower()

            error_details = {
                'error_code': err_resp.get('error_code', 'N/A'),
                'description': err_resp.get('description', 'N/A'),
                'message': err_resp.get('message', 'N/A'),
                'status': err_resp.get('status', 'N/A')
            }

            is_auth_error = (
                'unauthorized' in error_str or
                '401' in error_str or
                'unauthorized' in error_code or
                'unauthorized' in description or
                'unauthorized' in message or
                'expired' in error_str or
                'token' in error_str
            )
        except Exception as parse_err:
            # Fallback to string matching
            is_auth_error = 'unauthorized' in error_str or '401' in error_str
            error_details = {'raw_error': str(e)}

        if is_auth_error:
            print(f"   ❌ Authentication error: {e}")
            if error_details:
                print(f"   Error details: {json.dumps(error_details, indent=6)}")
            print("\n   💡 Troubleshooting steps:")
            print("      1. Verify you're logged into the profile:")
            if profile_name and profile_name in ['global', 'china']:
                if profile_name == 'global':
                    print("         esp-rainmaker-cli login")
                else:
                    print(f"         esp-rainmaker-cli login --profile {profile_name}")
            else:
                print("         esp-rainmaker-cli login")
                print("         # Or for china profile:")
                print("         esp-rainmaker-cli login --profile china")
            print("      2. Check your profile configuration:")
            print("         esp-rainmaker-cli getnodes")
            print("      3. Try using --diagnose flag for more info:")
            print("         python3 examples/control_device.py --diagnose")
        else:
            print(f"   ❌ HTTP error: {e}")
            if error_details:
                print(f"   Error details: {json.dumps(error_details, indent=6)}")
        return []
    except (NetworkError, RequestTimeoutError) as e:
        print(f"   ❌ Network error: {e}")
        return []
    except SSLError as e:
        print(f"   ❌ SSL error: {e}")
        return []
    except Exception as e:
        error_str = str(e).lower()
        if 'unauthorized' in error_str:
            print(f"   ❌ Authentication error: {e}")
            print("\n   💡 Your session may have expired. Please login again:")
            print("      esp-rainmaker-cli login")
        else:
            print(f"   ❌ Error listing nodes: {e}")
        return []


def get_node_params(node_obj, use_local=False, use_auto=False, pop=None, node_cache=None, session_store=None):
    """
    Get parameters from a node.

    :param node_obj: Node object
    :param use_local: Whether to use local control only
    :param use_auto: Whether to try local first, then fall back to cloud
    :param pop: Proof of Possession for local control (optional with --auto)
    :param node_cache: Optional NodeCache for auto-resolving POP
    :param session_store: Optional SessionStore for session reuse
    :return: Parameters dictionary or None
    """
    node_id = node_obj.get_nodeid()
    print(f"\n📥 Getting parameters from node {node_id}...")

    # Auto-resolve POP if using --auto and POP not provided (silent if already resolved)
    if use_auto and not pop:
        pop = auto_resolve_pop(node_obj, node_cache, silent=True)
        if not pop:
            print("   ⚠️  Could not auto-resolve POP, falling back to cloud...")

    # Try local control if --local or --auto is specified and we have POP
    if (use_local or use_auto) and pop:
        try:
            from rmaker_lib.local_control import run_local_control_operation
            if use_auto:
                print("   Trying local control first (--auto)...")
            else:
                print("   Using local control (faster)...")
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
                print("   ✅ Successfully retrieved parameters via local control")
                return result
            else:
                if use_auto:
                    print("   ⚠️  Local control failed, falling back to cloud...")
                else:
                    print("   ⚠️  Local control failed")
                    return None
        except Exception as e:
            if use_auto:
                print(f"   ⚠️  Local control error: {e}, falling back to cloud...")
            else:
                print(f"   ❌ Local control error: {e}")
                return None

    # Fall back to cloud API (for --auto or if local not specified)
    if use_auto or not use_local:
        try:
            params = node_obj.get_node_params()
            if params:
                if use_auto:
                    print("   ✅ Successfully retrieved parameters via cloud")
                else:
                    print("   ✅ Successfully retrieved parameters via cloud")
                return params
            else:
                print("   ❌ Failed to retrieve parameters")
                return None
        except (NetworkError, RequestTimeoutError) as e:
            print(f"   ❌ Network error: {e}")
            return None
        except HttpErrorResponse as e:
            print(f"   ❌ HTTP error: {e}")
            return None
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return None

    return None


def set_node_params(node_obj, params_data, use_local=False, use_auto=False, pop=None, node_cache=None, session_store=None):
    """
    Set parameters on a node.

    :param node_obj: Node object
    :param params_data: Dictionary of parameters to set
    :param use_local: Whether to use local control only
    :param use_auto: Whether to try local first, then fall back to cloud
    :param pop: Proof of Possession for local control (optional with --auto)
    :param node_cache: Optional NodeCache for auto-resolving POP
    :param session_store: Optional SessionStore for session reuse
    :return: True if successful, False otherwise
    """
    node_id = node_obj.get_nodeid()
    print(f"\n📤 Setting parameters on node {node_id}...")
    print(f"   Parameters: {json.dumps(params_data, indent=2)}")

    # Auto-resolve POP if using --auto and POP not provided (silent if already resolved)
    if use_auto and not pop:
        pop = auto_resolve_pop(node_obj, node_cache, silent=True)
        if not pop:
            print("   ⚠️  Could not auto-resolve POP, falling back to cloud...")

    # Try local control if --local or --auto is specified and we have POP
    if (use_local or use_auto) and pop:
        try:
            from rmaker_lib.local_control import run_local_control_operation
            if use_auto:
                print("   Trying local control first (--auto)...")
            else:
                print("   Using local control (faster)...")
            result = run_local_control_operation(
                node_id,
                'set_params',
                data=params_data,
                pop=pop,
                transport='http',
                port=8080,
                sec_ver=1,
                node_cache=node_cache,
                session_store=session_store
            )
            if result:
                print("   ✅ Successfully set parameters via local control")
                return True
            else:
                if use_auto:
                    print("   ⚠️  Local control failed, falling back to cloud...")
                else:
                    print("   ⚠️  Local control failed")
                    return False
        except Exception as e:
            if use_auto:
                print(f"   ⚠️  Local control error: {e}, falling back to cloud...")
            else:
                print(f"   ❌ Local control error: {e}")
                return False

    # Fall back to cloud API (for --auto or if local not specified)
    if use_auto or not use_local:
        try:
            success = node_obj.set_node_params(params_data)
            if success:
                if use_auto:
                    print("   ✅ Successfully set parameters via cloud")
                else:
                    print("   ✅ Successfully set parameters via cloud")
                return True
            else:
                print("   ❌ Failed to set parameters")
                return False
        except (NetworkError, RequestTimeoutError) as e:
            print(f"   ❌ Network error: {e}")
            return False
        except HttpErrorResponse as e:
            print(f"   ❌ HTTP error: {e}")
            return False
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False

    return False


def get_node_status(node_obj):
    """
    Get the online/offline status of a node.

    :param node_obj: Node object
    :return: Status dictionary or None
    """
    node_id = node_obj.get_nodeid()
    print(f"\n📊 Getting status of node {node_id}...")

    try:
        status = node_obj.get_node_status()
        if status:
            online = status.get('status', {}).get('online', False)
            if online:
                status_str = "🟢 Online"
                print(f"   {status_str}")
            else:
                status_str = "🔴 Offline (cloud status)"
                print(f"   {status_str}")
                print("   💡 Note: Device may still be reachable via local control")
            return status
        return None
    except Exception as e:
        print(f"   ❌ Error getting status: {e}")
        return None


def get_node_config(node_obj, use_local=False, use_auto=False, pop=None, node_cache=None, session_store=None):
    """
    Get configuration from a node.

    :param node_obj: Node object
    :param use_local: Whether to use local control only
    :param use_auto: Whether to try local first, then fall back to cloud
    :param pop: Proof of Possession for local control (optional with --auto)
    :param node_cache: Optional NodeCache for auto-resolving POP
    :param session_store: Optional SessionStore for session reuse
    :return: Configuration dictionary or None
    """
    node_id = node_obj.get_nodeid()
    print(f"\n⚙️  Getting configuration from node {node_id}...")

    # Auto-resolve POP if using --auto and POP not provided (silent if already resolved)
    if use_auto and not pop:
        pop = auto_resolve_pop(node_obj, node_cache, silent=True)
        if not pop:
            print("   ⚠️  Could not auto-resolve POP, falling back to cloud...")

    # Try local control if --local or --auto is specified and we have POP
    if (use_local or use_auto) and pop:
        try:
            from rmaker_lib.local_control import run_local_control_operation
            if use_auto:
                print("   Trying local control first (--auto)...")
            else:
                print("   Using local control (faster)...")
            result = run_local_control_operation(
                node_id,
                'get_config',
                pop=pop,
                transport='http',
                port=8080,
                sec_ver=1,
                node_cache=node_cache,
                session_store=session_store
            )
            if result:
                print("   ✅ Successfully retrieved configuration via local control")
                return result
            else:
                if use_auto:
                    print("   ⚠️  Local control failed, falling back to cloud...")
                else:
                    print("   ⚠️  Local control failed")
                    return None
        except Exception as e:
            if use_auto:
                print(f"   ⚠️  Local control error: {e}, falling back to cloud...")
            else:
                print(f"   ❌ Local control error: {e}")
                return None

    # Fall back to cloud API (for --auto or if local not specified)
    if use_auto or not use_local:
        try:
            config = node_obj.get_node_config()
            if config:
                if use_auto:
                    print("   ✅ Successfully retrieved configuration via cloud")
                else:
                    print("   ✅ Successfully retrieved configuration via cloud")
                return config
            else:
                print("   ❌ Failed to retrieve configuration")
                return None
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return None

    return None


def print_params(params, indent=0):
    """
    Pretty print parameters in a readable format.

    :param params: Parameters dictionary
    :param indent: Indentation level
    """
    if not params:
        return

    prefix = "   " * indent

    # Handle different parameter structures
    if 'params' in params:
        # Cloud API response format
        params_data = params['params']
    elif 'node' in params:
        # Alternative cloud API format
        params_data = params['node']
    else:
        # Direct parameters or local control format
        params_data = params

    if isinstance(params_data, dict):
        for device_name, device_params in params_data.items():
            if isinstance(device_params, dict):
                print(f"{prefix}📱 {device_name}:")
                for param_name, param_value in device_params.items():
                    print(f"{prefix}   • {param_name}: {param_value}")
            else:
                print(f"{prefix}📱 {device_name}: {device_params}")
    else:
        print(f"{prefix}{json.dumps(params_data, indent=2)}")


def main():
    """Main function to demonstrate device control."""
    parser = argparse.ArgumentParser(
        description='ESP RainMaker Device Control Example',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all nodes
  python3 examples/control_device.py

  # Control a specific node
  python3 examples/control_device.py --node-id YOUR_NODE_ID

  # Use local control (faster, requires POP)
  python3 examples/control_device.py --node-id YOUR_NODE_ID --local --pop YOUR_POP

  # Use auto mode (tries local first, falls back to cloud)
  python3 examples/control_device.py --node-id YOUR_NODE_ID --auto

  # Set parameters from command line
  python3 examples/control_device.py --node-id YOUR_NODE_ID --set-params '{"Light": {"Power": true, "Brightness": 75}}'

  # Get parameters only
  python3 examples/control_device.py --node-id YOUR_NODE_ID --get-only
        """
    )
    parser.add_argument(
        '--node-id',
        type=str,
        help='Node ID to control (if not provided, will list all nodes)'
    )
    parser.add_argument(
        '--local',
        action='store_true',
        help='Use local control (faster, requires --pop)'
    )
    parser.add_argument(
        '--auto',
        action='store_true',
        help='Try local control first, fall back to cloud if local fails'
    )
    parser.add_argument(
        '--pop',
        type=str,
        help='Proof of Possession for local control (optional with --auto, will be auto-resolved from cache or cloud)'
    )
    parser.add_argument(
        '--get-only',
        action='store_true',
        help='Only get parameters, do not set any'
    )
    parser.add_argument(
        '--set-params',
        type=str,
        help='JSON string of parameters to set (e.g., \'{"Light": {"Power": true, "Brightness": 75}}\')'
    )
    parser.add_argument(
        '--profile',
        type=str,
        help='Profile name to use (optional)'
    )
    parser.add_argument(
        '--diagnose',
        action='store_true',
        help='Show diagnostic information about the session'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("ESP RainMaker Device Control Example")
    print("=" * 60)

    # Initialize session
    print("\n🔐 Initializing session...")

    # Use specified profile or default to global
    profile_to_use = args.profile if args.profile else 'global'

    if args.profile:
        print(f"   Using specified profile: {profile_to_use}")
    else:
        print(f"   Using default profile: {profile_to_use}")

    # Check tokens before trying to create session (for better error messages)
    try:
        from rmaker_lib import configmanager
        temp_config = configmanager.Config(profile_override=profile_to_use)
        has_tokens = temp_config.profile_manager.has_profile_tokens(profile_to_use)

        if not has_tokens:
            print(f"   ❌ Profile '{profile_to_use}' does not have tokens")

            # Check which profiles DO have tokens
            print("\n   Checking which profiles have tokens...")
            profiles_with_tokens = []
            for prof_name in ['global', 'china']:
                try:
                    if temp_config.profile_manager.has_profile_tokens(prof_name):
                        profiles_with_tokens.append(prof_name)
                        print(f"      ✅ {prof_name}: Has tokens")
                    else:
                        print(f"      ❌ {prof_name}: No tokens")
                except:
                    print(f"      ⚠️  {prof_name}: Could not check")

            if profiles_with_tokens:
                print(f"\n   💡 Found tokens in: {', '.join(profiles_with_tokens)}")
                print(f"      You can use: python3 examples/control_device.py --profile {profiles_with_tokens[0]}")

            print(f"\n   💡 To login to '{profile_to_use}' profile:")
            if profile_to_use == 'global':
                print("      esp-rainmaker-cli login --profile global")
            else:
                print(f"      esp-rainmaker-cli login --profile {profile_to_use}")
            print("\n   Note: Make sure to specify --profile when logging in!")
            sys.exit(1)
    except Exception as check_err:
        # If check fails, still try to create session - let it handle the error
        log.debug(f"Token check failed: {check_err}")

    try:
        # Try to create session - it will check for tokens and give proper error if missing
        sess = session.Session(profile_override=profile_to_use)
        print("   ✅ Session initialized successfully")

        # Show profile information
        current_profile = sess.config.get_current_profile_name()
        print(f"   Profile: {current_profile}")
        print(f"   Region: {sess.config.get_region()}")

        # Validate and refresh token if needed
        try:
            # This will automatically refresh if expired
            token = sess.config.get_access_token()
            if token:
                print("   ✅ Access token validated")
                # Update session header in case token was refreshed
                sess.id_token = token
                sess.request_header = {'Content-Type': 'application/json',
                                      'Authorization': token}
        except Exception as token_err:
            print(f"   ⚠️  Token validation issue: {token_err}")
            print("\n   💡 Please login again:")
            if current_profile == 'global':
                print("      esp-rainmaker-cli login")
            else:
                print(f"      esp-rainmaker-cli login --profile {current_profile}")
            sys.exit(1)

        # Run diagnostics if requested
        if args.diagnose:
            diagnose_session(sess, profile_name=profile_to_use)
            print("\n" + "=" * 60)

    except InvalidConfigError as e:
        print(f"   ❌ Configuration error: {e}")
        print("\n   💡 Please login first:")
        print("      esp-rainmaker-cli login")
        print("\n   Or if you're using a profile:")
        print("      esp-rainmaker-cli login --profile PROFILE_NAME")
        sys.exit(1)
    except Exception as e:
        error_str = str(e).lower()
        if 'unauthorized' in error_str or 'expired' in error_str or 'token' in error_str:
            print(f"   ❌ Authentication error: {e}")
            print("\n   💡 Your session may have expired. Please login again:")
            print("      esp-rainmaker-cli login")
        else:
            print(f"   ❌ Error initializing session: {e}")
        sys.exit(1)

    # List nodes if node-id not provided
    if not args.node_id:
        nodes = list_nodes(sess, profile_name=args.profile)
        if not nodes:
            print("\n💡 Tip: Use --node-id to control a specific device")
            print("   Example: python3 examples/control_device.py --node-id YOUR_NODE_ID")
            sys.exit(0)

        # Use first node if multiple exist
        if len(nodes) == 1:
            args.node_id = nodes[0].get('id')
            print(f"\n   Using node: {args.node_id}")
        else:
            print("\n   Please specify a node ID using --node-id")
            print("   Example: python3 examples/control_device.py --node-id YOUR_NODE_ID")
            sys.exit(0)

    # Create node object
    node_obj = node.Node(args.node_id, sess)

    # Get cache objects for auto POP resolution and session reuse (CRITICAL for performance!)
    # Automatically enable cache for --auto and --local to enable session reuse
    # Session reuse reduces latency from ~10s (first call) to < 1s (subsequent calls)
    node_cache = None
    session_store = None
    if args.auto or args.local:
        try:
            from rmaker_lib.node_cache import NodeCache, is_cache_enabled, _get_cache_base_dir
            from rmaker_lib.session_store import SessionStore
            profile_config = sess.config.get_profile_config_for_current()

            # Automatically enable cache if not already enabled (for better performance)
            cache_enabled = is_cache_enabled(profile_config, no_cache_flag=False)
            if not cache_enabled:
                try:
                    sess.config.profile_manager.set_cache_enabled(profile_to_use, True)
                    profile_config = sess.config.get_profile_config_for_current()  # Refresh config
                    cache_enabled = True
                    print("   ✅ Cache automatically enabled for better performance")
                except Exception as e:
                    log.debug(f"Failed to auto-enable cache: {e}")

            try:
                user_id = sess.config.get_user_id()
            except:
                user_id = 'unknown'

            base_dir = _get_cache_base_dir(profile_config)
            cache_dir = os.path.join(base_dir, profile_to_use, user_id or 'unknown')

            # Initialize cache objects (now that cache is enabled)
            node_cache = NodeCache(profile_to_use, user_id, enabled=True)
            session_store = SessionStore(cache_dir, enabled=True)

            if cache_enabled:
                print("   ✅ Cache enabled - POP and sessions will be cached for faster subsequent calls")
        except Exception as e:
            log.debug(f"Failed to initialize cache: {e}")

    # Resolve POP once at the beginning if using --auto (to avoid repeated cloud calls)
    resolved_pop = args.pop
    if (args.auto or args.local) and not resolved_pop:
        resolved_pop = auto_resolve_pop(node_obj, node_cache, silent=False)

    # Get node status
    get_node_status(node_obj)

    # Get node configuration
    config = get_node_config(node_obj, use_local=args.local, use_auto=args.auto, pop=resolved_pop, node_cache=node_cache, session_store=session_store)
    if config:
        print(f"\n   Configuration keys: {list(config.keys())}")

    # Get current parameters
    params = get_node_params(node_obj, use_local=args.local, use_auto=args.auto, pop=resolved_pop, node_cache=node_cache, session_store=session_store)
    if params:
        print("\n📋 Current Parameters:")
        print_params(params)

    # If get-only, exit here
    if args.get_only:
        print("\n✅ Done!")
        return

    # Set parameters if provided via command line
    params_to_set = None
    if args.set_params:
        try:
            params_to_set = json.loads(args.set_params)
            print("\n" + "=" * 60)
            print("Setting Parameters")
            print("=" * 60)
        except json.JSONDecodeError as e:
            print(f"\n❌ Invalid JSON in --set-params: {e}")
            print("   Example: --set-params '{\"Light\": {\"Power\": true, \"Brightness\": 75}}'")
            sys.exit(1)
    else:
        # Example: Set parameters (modify based on your device)
        # This is a generic example - adjust based on your device's parameters
        print("\n" + "=" * 60)
        print("Example: Setting Parameters")
        print("=" * 60)
        print("\n💡 Note: Modify the parameters below based on your device type")
        print("   Common device types: Light, Switch, Fan, Thermostat, etc.")
        print("\n   Or use --set-params to set parameters from command line:")
        print("   python3 examples/control_device.py --node-id YOUR_NODE_ID --set-params '{\"Light\": {\"Power\": true}}'")

        # Example parameters - adjust these based on your device
        example_params = {
            # Example for a Light device:
            # "Light": {
            #     "Power": True,
            #     "Brightness": 75
            # }

            # Example for a Switch device:
            # "Switch": {
            #     "Power": True
            # }

            # Example for a Fan device:
            # "Fan": {
            #     "Power": True,
            #     "Speed": 3
            # }
        }
        params_to_set = example_params

    if params_to_set:
        success = set_node_params(
            node_obj,
            params_to_set,
            use_local=args.local,
            use_auto=args.auto,
            pop=resolved_pop,
            node_cache=node_cache,
            session_store=session_store
        )
        if success:
            # Get updated parameters
            print("\n⏳ Waiting 2 seconds for device to update...")
            import time
            time.sleep(2)
            updated_params = get_node_params(
                node_obj,
                use_local=args.local,
                use_auto=args.auto,
                pop=resolved_pop,
                node_cache=node_cache,
                session_store=session_store
            )
            if updated_params:
                print("\n📋 Updated Parameters:")
                print_params(updated_params)
    else:
        print("\n   No example parameters set. Modify the script to add your device parameters.")
        print("\n   Example for a Light device:")
        print('   example_params = {"Light": {"Power": True, "Brightness": 75}}')

    print("\n" + "=" * 60)
    print("✅ Example completed!")
    print("=" * 60)
    print("\n💡 Tips:")
    print("   - Use --auto to try local control first, fall back to cloud automatically")
    print("   - With --auto, POP is auto-resolved from cache or cloud (no --pop needed!)")
    print("   - Use --local --pop YOUR_POP for local-only control (faster)")
    print("   - Check device documentation for available parameters")
    print("   - Use getparams command to see current device structure:")
    print("     esp-rainmaker-cli getparams YOUR_NODE_ID")


if __name__ == '__main__':
    main()
