# Bosgame M5 Fan Control

GTK4/libadwaita GUI and systemd service for controlling fans on Bosgame M5 / Sixunited AXB35-02 boards.

## Features

- Control 3 fans (CPU Fan 1, CPU Fan 2, System Fan)
- Fan modes: auto, fixed, curve
- Custom temperature curves with hysteresis
- APU power modes: quiet, balanced, performance
- Real-time temperature monitoring (CPU, GPU, NVMe, WiFi, Ethernet)
- Systemd service for persistent settings

## Requirements

- Linux kernel with ec_su_axb35 driver (from [cmetz/ec-su_axb35-linux](https://github.com/cmetz/ec-su_axb35-linux))
- Python 3
- GTK4, libadwaita
- python-gobject

## Installation

```bash
# Install the ec_su_axb35 driver first (see driver repo)

# Then install fan control:
sudo make install

# Enable autostart
sudo systemctl enable bosgame-fan-control.service
```

## Usage

### GUI
```bash
bosgame-fan-control
```

### Command Line
```bash
# Check status
sudo fan-control.sh status

# Apply settings from config
sudo fan-control.sh start
```

### Manual Control
```bash
# Set fan mode (auto/fixed/curve)
echo curve > /sys/class/ec_su_axb35/fan1/mode

# Set fan level (0-5)
echo 3 > /sys/class/ec_su_axb35/fan1/level

# Set custom curves (comma-separated temps for levels 1-5)
echo "60,70,80,88,95" > /sys/class/ec_su_axb35/fan1/rampup_curve
echo "50,60,70,78,85" > /sys/class/ec_su_axb35/fan1/rampdown_curve

# Set power mode (quiet/balanced/performance)
echo balanced > /sys/class/ec_su_axb35/apu/power_mode
```

## Configuration

Edit `/etc/bosgame-fan-control.conf`:

```bash
POWER_MODE="balanced"
FAN_MODE="curve"
RAMPUP_CURVE="60,70,80,88,95"
RAMPDOWN_CURVE="50,60,70,78,85"
```

## Supported Devices

- Bosgame M5
- GMKtec EVO-X2
- FEVM FA-EX9
- Peladn YO1
- Other Sixunited AXB35-02 based devices

## License

MIT
