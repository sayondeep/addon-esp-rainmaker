# ESP RainMaker CLI Examples

This directory contains example programs demonstrating how to use the ESP RainMaker CLI library to control and interact with ESP RainMaker devices.

## Examples

### control_device.py

A comprehensive example demonstrating how to:
- Initialize a session with ESP RainMaker
- List available nodes
- Get node status, configuration, and parameters
- Set node parameters
- Use local control for faster operations

#### Prerequisites

1. **Install ESP RainMaker CLI** (if not already installed):
   ```bash
   pip3 install esp-rainmaker-cli
   ```

2. **Login to ESP RainMaker**:
   ```bash
   esp-rainmaker-cli login
   ```

3. **Claim a device** (if you haven't already):
   ```bash
   esp-rainmaker-cli claim --pop YOUR_POP
   ```

#### Usage

**List all nodes:**
```bash
python3 examples/control_device.py
```

**Control a specific node:**
```bash
python3 examples/control_device.py --node-id YOUR_NODE_ID
```

**Use local control (faster, requires POP):**
```bash
python3 examples/control_device.py --node-id YOUR_NODE_ID --local --pop YOUR_POP
```

**Get parameters only:**
```bash
python3 examples/control_device.py --node-id YOUR_NODE_ID --get-only
```

**Use a specific profile:**
```bash
python3 examples/control_device.py --node-id YOUR_NODE_ID --profile PROFILE_NAME
```

#### Customizing for Your Device

The example includes placeholder code for setting parameters. To control your specific device:

1. First, check your device's current parameters:
   ```bash
   esp-rainmaker-cli getparams YOUR_NODE_ID
   ```

2. Modify the `example_params` dictionary in `control_device.py` based on your device type:

   **For a Light device:**
   ```python
   example_params = {
       "Light": {
           "Power": True,
           "Brightness": 75,
           "Hue": 120,
           "Saturation": 100
       }
   }
   ```

   **For a Switch device:**
   ```python
   example_params = {
       "Switch": {
           "Power": True
       }
   }
   ```

   **For a Fan device:**
   ```python
   example_params = {
       "Fan": {
           "Power": True,
           "Speed": 3
       }
   }
   ```

   **For a Thermostat:**
   ```python
   example_params = {
       "Thermostat": {
           "Mode": "Cooling",
           "Temperature": 22
       }
   }
   ```

3. Run the script again to control your device.

#### Local Control

Local control provides 5-10x faster response times by communicating directly with the device on your local network instead of going through the cloud.

**Benefits:**
- Faster response times (50-200ms vs 500-2000ms)
- Works offline (no internet required)
- Reduced bandwidth usage
- Enhanced privacy (data stays on local network)

**Requirements:**
- Device must be on the same local network
- Proof of Possession (POP) value is required
- Device must support ESP Local Control

**Finding your POP:**
- Check your device's documentation
- It's usually provided during device claiming
- You can also check node configuration:
  ```bash
  esp-rainmaker-cli getnodeconfig YOUR_NODE_ID
  ```

#### Error Handling

The example includes comprehensive error handling for:
- Network errors
- Authentication errors
- Invalid node IDs
- Local control failures (with automatic fallback to cloud)

#### Code Structure

The example demonstrates:
- Session initialization
- Node management
- Parameter retrieval (cloud and local)
- Parameter setting (cloud and local)
- Status checking
- Configuration retrieval
- Pretty printing of results

## Additional Resources

- [ESP RainMaker Documentation](https://github.com/espressif/esp-rainmaker)
- [CLI Usage Guide](../docs/README.md)
- [Parameter Management](../docs/commands/parameters.md)
- [Local Control Guide](../docs/commands/local_control.md)
