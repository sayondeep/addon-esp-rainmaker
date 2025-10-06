# ESP RainMaker Add-on

ESP RainMaker integration addon for Home Assistant. Control and monitor your ESP RainMaker devices directly from Home Assistant.

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]
![Supports armhf Architecture][armhf-shield]
![Supports armv7 Architecture][armv7-shield]
![Supports i386 Architecture][i386-shield]

## About

This addon provides ESP RainMaker integration for Home Assistant, allowing you to control and monitor your ESP RainMaker devices directly from Home Assistant.

## Features

- Automatic discovery of ESP RainMaker devices
- Control lights and switches with full brightness and color support
- Monitor device status and parameters
- Real-time updates from ESP RainMaker cloud
- Responsive device control with optimized polling
- Device name synchronization
- Professional ESP RainMaker branding

## Installation

1. Add this repository to your Home Assistant:
   - Go to **Supervisor** → **Add-on Store**
   - Click the **⋮** menu in the top right
   - Select **Repositories**
   - Add: `https://github.com/sayondeep/addon-esp-rainmaker`

2. Install the "ESP RainMaker" add-on

3. Configure your ESP RainMaker credentials

4. Start the add-on

5. Add the ESP RainMaker integration:
   - Go to **Settings** → **Devices & Services**
   - Click **Add Integration**
   - Search for **ESP RainMaker**
   - Configure with Host: `addon_esp-rainmaker` and Port: `8100`

## Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `email` | Your ESP RainMaker account email | - |
| `password` | Your ESP RainMaker account password | - |
| `profile` | ESP RainMaker profile to use | `global` |
| `api_port` | Port for the internal API | `8100` |

### Example Configuration

```yaml
email: "your.email@example.com"
password: "your_password"
profile: "global"
api_port: 8100
```

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/sayondeep/addon-esp-rainmaker/issues).

## Changelog & Releases

This repository follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[armhf-shield]: https://img.shields.io/badge/armhf-yes-green.svg
[armv7-shield]: https://img.shields.io/badge/armv7-yes-green.svg
[i386-shield]: https://img.shields.io/badge/i386-yes-green.svg