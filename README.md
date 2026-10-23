# ConnectSmartHome for Home Assistant — experimental

A HACS custom integration that attempts to authorize a **ConnectSmartHome**
account using its **User Code and in-app QR scanner**, with device platforms
adapted from Home Assistant's official Tuya integration (Core 2026.10.3).

**Status: experimental. ConnectSmartHome QR approval and device control have
not yet been verified.** A successful QR-token request alone does not prove
that the app will approve it. Some Tuya OEM apps reject this service:
[upstream SDK issue #43](https://github.com/tuya/tuya-device-sharing-sdk/issues/43).
An app-side authorization restriction cannot be removed by renaming a component.

## Install with HACS

Requires **Home Assistant 2026.10.3 or later** and HACS.

1. In HACS, open the three-dot menu → **Custom repositories**.
2. Add `https://github.com/FoxyOwl833/connectsmarthome-hacs` as **Integration**.
3. Find **ConnectSmartHome (Experimental)** and download it.
4. Restart Home Assistant.
5. Open **Settings → Devices & services → Add integration** and choose
   **ConnectSmartHome (Experimental)**.
6. Enter the User Code from **ConnectSmartHome → Settings → Account and Security**.
7. In ConnectSmartHome, open **+ → Scan** (or the app's scanner), scan the code,
   approve access, and select **Submit** in Home Assistant.

HACS custom-repository installation does not require this repository to appear
in HACS's default catalogue. Do not add it under Dashboard resources.

For manual installation, copy `custom_components/connectsmarthome` into your
Home Assistant `config/custom_components/` folder and restart.

## What it includes

Separate integration and device identifiers allow installation alongside Tuya.
The copied upstream platforms cover alarms, binary sensors, buttons, cameras,
climate, covers, events, fans, humidifiers, lights, numbers, scenes, selects,
sensors, sirens, switches, vacuums, and valves. Actual available entities depend
on the device data and permissions returned by Tuya's sharing SDK.
This remains a cloud integration, requiring internet access.

The app-specific setup labels do **not** change Tuya's published authorization
registration (`haauthorize`) or QR wire prefix (`tuyaSmart--qrLogin`). The
ConnectSmartHome User Code identifies the account; app-side permission is still
required. No guessed CSH endpoint, app secret, or private API is used.

## Troubleshooting

- **QR not accepted by the app:** report the exact message, app version and region.
  ConnectSmartHome/Tuya may need to enable device-sharing authorization.
- **Pressed Submit early:** scan and approve the same code, then Submit again.
- **Expired code:** select **Refresh QR code**, Submit, then scan the new code.
- **Missing devices or features:** reload the integration after adding devices.
  Download device diagnostics to inspect the SDK's exposed data.
- **Expired credentials:** Home Assistant starts a new QR authentication flow.
  Reauthenticate with the same account.

Never attach User Codes, QR tokens, passwords, or access/refresh tokens to issues.
Sessions live in Home Assistant's config entries; they are not stored in this
repository. Optional device quirks use `config/connectsmarthome_quirks`.

## Development and validation

`python -m compileall -q custom_components` checks syntax.
`pytest tests/unit` exercises the real configuration-flow code with a small
Home Assistant API adapter on platforms where HA cannot run. These tests cover
pairing state transitions and error handling, and are not an HA runtime test.
The GitHub workflow also runs real Home Assistant flow tests on Linux.
Live ConnectSmartHome app approval and physical device tests are still required.

## Attribution

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for the upstream source
and modifications. This is an independent community experiment.
