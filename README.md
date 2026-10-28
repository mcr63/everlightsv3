# EverLights v3 (Local)

A HACS-installable Home Assistant integration for EverLights v3 bridges. All control happens locally over HTTP on port 80; no cloud connection is needed. It can coexist with integrations using the old `everlights` domain because its domain is `everlights_v3`.

Features include RGB zone lights, brightness, all 13 effects, bridge presets, a visual pattern editor, zone playlists, diagnostic entities, and automatic bridge clock synchronization.

## Install with HACS

HACS > ⋮ > Custom repositories > enter `https://github.com/mcr63/everlightsv3` > category **Integration** > download > restart Home Assistant > Settings > Devices & services > Add integration > **EverLights v3 (Local)** > enter your bridge IP (for example `192.168.x.x`).

Requires Home Assistant 2024.10.0 or later. For manual installation, copy `custom_components/everlights_v3` into your Home Assistant `custom_components` directory, restart, and add the integration through Devices & services.

## Options and entities

Each bridge has options for polling interval (10 seconds by default, range 5–300), clock synchronization (enabled), and sidebar panel (enabled). Changing options reloads the integration.

Each zone has an RGB light and a Playlist switch. Lights expose current pattern, effects, and alias as attributes. Zone diagnostics include RSSI, SNR, and reboot count. Bridge diagnostics include reboot count, cloud outage duration, firmware, and Cloud reachable. Noisy diagnostic entities start disabled; enable them in the entity settings if needed.

The bridge updates active state a few seconds after a command. The integration requests a refresh after five seconds. Brightness scales pattern RGB channels; the bridge has no separate brightness field. An unscaled pattern is kept in memory and restored across Home Assistant restarts to avoid rounding loss when changing brightness repeatedly. Plain turn-on restores the previous pattern, or starts with warm white `FF9A3C`.

## Services

Services target zone light entities, except `set_time`, which addresses all bridges or an optional `config_entry_id`. Presets belong to the targeted light's bridge. Names matching an existing user preset update it. Factory presets can be played but cannot be deleted.

```yaml
action: everlights_v3.set_pattern
target:
  entity_id: light.front_lights
data:
  colors: ["#FF9A3C", [255, 30, 0]]
  effects:
    - type: fade
      value: 128
    - type: chase
      value: 90
  brightness: 200
  alias: Evening
```

```yaml
action: everlights_v3.save_preset
target:
  entity_id: light.front_lights
data:
  name: Evening
  colors: ["FF9A3C", "FF2200"]
  effects:
    - type: twinkle
      value: 100
```

```yaml
action: everlights_v3.play_preset
target:
  entity_id: light.front_lights
data:
  preset: Evening # alias or preset ID
```

```yaml
action: everlights_v3.delete_preset
target:
  entity_id: light.front_lights
data:
  preset: Evening
```

```yaml
action: everlights_v3.start_playlist
target:
  entity_id: light.front_lights
data:
  presets: [Evening, Sunset]
  interval: 60 # seconds, 5–86400
  shuffle: false
```

```yaml
action: everlights_v3.stop_playlist
target:
  entity_id: light.front_lights
```

```yaml
action: everlights_v3.set_time
data: {} # optionally config_entry_id: your entry ID
```

Manual pattern changes, preset playback, and turning a light off stop its playlist. The Playlist switch resumes the last list during the current integration session. Playlists stop when the integration unloads; they are not bridge schedules and require Home Assistant to remain running.

## Effects and panel

Modifiers `fade`, `blink`, `strobe`, and `lightning` stack. Motion effects are `bars`, `gradient`, `random`, `wipe`, `melt`, `twinkle`, `chase`, `reverseChase`, and `pingPong`. One motion effect is recommended, although the bridge accepts multiple. Effect values range from 0–255 and are clamped by the integration. Blue LEDs are bright: warm whites should use less blue.

The **EverLights** sidebar panel is available to administrators. Pick a zone, edit colors and multiple effects, view animated approximations, adjust brightness, send a pattern, and save or play bridge presets. Add gallery patterns to a playlist and start or stop it from the panel. Previews approximate the hardware effects.

You can block the bridge's internet access in your router and keep full local control. The integration keeps the bridge clock in sync at setup and every six hours, unless disabled in options.

## Development

Run `python tools/panel/build.py` to build the standalone panel preview from the shipped JavaScript. Run `python tools/panel/test_preview.py` when Playwright and its Chromium browser are installed. Run `python -m pytest` for helper and integration tests; HA tests use `pytest-homeassistant-custom-component` and mocked HTTP responses.

## Credits

Based on the original integration by [theOrakle/everlightsv3](https://github.com/theOrakle/everlightsv3), from which this repository was forked. API research and ideas: [CWSpear/everlights](https://github.com/CWSpear/everlights), [weswitt/everlights3](https://github.com/weswitt/everlights3), and [martin-robert-fink/savant-everlights](https://github.com/martin-robert-fink/savant-everlights).

MIT licensed. Not affiliated with EverLights.
