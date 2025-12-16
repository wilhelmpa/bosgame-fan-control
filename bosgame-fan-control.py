#!/usr/bin/env python3
"""
Bosgame M5 Fan Control GUI
A GTK4/libadwaita application for controlling fans on Bosgame M5 / Sixunited AXB35 boards
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio
import os
import subprocess
import shutil

SYSFS_BASE = "/sys/class/ec_su_axb35"

# All temperature sensors to monitor
TEMP_SENSORS = [
    {"path": "/sys/class/hwmon/hwmon4/temp1_input", "name": "CPU (Tctl)", "divisor": 1000},
    {"path": "/sys/class/ec_su_axb35/temp1/temp", "name": "EC Sensor", "divisor": 1},
    {"path": "/sys/class/hwmon/hwmon1/temp1_input", "name": "GPU (Edge)", "divisor": 1000},
    {"path": "/sys/class/hwmon/hwmon2/temp1_input", "name": "NVMe 1", "divisor": 1000},
    {"path": "/sys/class/hwmon/hwmon3/temp1_input", "name": "NVMe 2", "divisor": 1000},
    {"path": "/sys/class/hwmon/hwmon7/temp1_input", "name": "WiFi", "divisor": 1000},
    {"path": "/sys/class/hwmon/hwmon5/temp1_input", "name": "Ethernet", "divisor": 1000},
]

# Power sensors (in microwatts)
POWER_SENSORS = [
    {"path": "/sys/devices/pci0000:00/0000:00:08.1/0000:c6:00.0/hwmon/hwmon3/power1_average", "name": "APU Power", "divisor": 1000000},
]

class FanControlApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.bosgame.fancontrol",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect('activate', self.on_activate)

    def on_activate(self, app):
        self.win = FanControlWindow(application=app)
        self.win.present()

class FanControlWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Bosgame M5 Fan Control")
        self.set_default_size(550, 1100)

        # Check if ryzenadj is available
        self.has_ryzenadj = shutil.which("ryzenadj") is not None

        # Main box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        # Header bar
        header = Adw.HeaderBar()
        main_box.append(header)

        # Refresh button
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.connect("clicked", self.refresh_all)
        header.pack_end(refresh_btn)

        # Scrolled window
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        main_box.append(scroll)

        # Content box
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_margin_top(8)
        content.set_margin_bottom(8)
        content.set_margin_start(8)
        content.set_margin_end(8)
        scroll.set_child(content)

        # Temperature card with all sensors
        self.temp_card, self.temp_labels = self.create_temp_card()
        content.append(self.temp_card)

        # Power display card
        self.power_display_card, self.power_labels = self.create_power_display_card()
        content.append(self.power_display_card)

        # Fan cards in a more compact layout
        self.fan_cards = {}
        for fan_id, fan_name in [("fan1", "CPU Fan 1"), ("fan2", "CPU Fan 2"), ("fan3", "System Fan")]:
            card = self.create_fan_card(fan_id, fan_name)
            self.fan_cards[fan_id] = card
            content.append(card["widget"])

        # Power mode card
        self.power_card = self.create_power_card()
        content.append(self.power_card)

        # Curve editor card
        self.curve_card = self.create_curve_card()
        content.append(self.curve_card)

        # GPU performance card
        self.gpu_card = self.create_gpu_card()
        content.append(self.gpu_card)

        # Ryzenadj tuning card (if available)
        if self.has_ryzenadj:
            self.tuning_card = self.create_tuning_card()
            content.append(self.tuning_card)

        # Flag for loading saved settings on first refresh
        self._first_load = True

        # Initial load
        self.refresh_all(None)

        # Auto-refresh every 2 seconds
        GLib.timeout_add_seconds(2, self.auto_refresh)

    def read_file(self, path):
        """Read any file"""
        try:
            with open(path, "r") as f:
                return f.read().strip()
        except:
            return None

    def read_sysfs(self, path):
        """Read a sysfs file from EC driver"""
        return self.read_file(f"{SYSFS_BASE}/{path}")

    def write_sysfs(self, path, value):
        """Write to a sysfs file directly"""
        try:
            full_path = f"{SYSFS_BASE}/{path}"
            with open(full_path, "w") as f:
                f.write(value)
            return True
        except PermissionError:
            self.show_error("Keine Berechtigung",
                "Führe aus:\nsudo /usr/local/bin/fan-control.sh start")
            return False
        except Exception as e:
            self.show_error("Fehler", str(e))
            return False

    def run_ryzenadj(self, *args):
        """Run ryzenadj with sudo (no password via sudoers)"""
        try:
            cmd = ["sudo", "ryzenadj"] + list(args)
            result = subprocess.run(cmd, capture_output=True, text=True)
            if "Sucessfully" in result.stdout or "Successfully" in result.stdout:
                return True
            if result.returncode != 0:
                self.show_error("ryzenadj Fehler", result.stderr or "Unbekannter Fehler")
                return False
            return True
        except Exception as e:
            self.show_error("Fehler", str(e))
            return False

    def save_tuning_config(self, stapm, fast, slow, temp, co, cogfx, gpu_level):
        """Save tuning settings to config file"""
        try:
            config_path = "/etc/bosgame-fan-control.conf"
            # Read existing config
            config = {}
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    for line in f:
                        if "=" in line and not line.strip().startswith("#"):
                            key, val = line.strip().split("=", 1)
                            config[key] = val.strip('"')

            # Update with tuning settings
            config["STAPM_LIMIT"] = str(stapm)
            config["FAST_LIMIT"] = str(fast)
            config["SLOW_LIMIT"] = str(slow)
            config["TEMP_LIMIT"] = str(temp)
            config["CPU_CO"] = str(co)
            config["GPU_CO"] = str(cogfx)
            config["GPU_LEVEL"] = gpu_level

            # Write back
            cmd = ["sudo", "tee", config_path]
            content = "\n".join([f'{k}="{v}"' for k, v in config.items()]) + "\n"
            subprocess.run(cmd, input=content, text=True, capture_output=True)
            return True
        except Exception as e:
            self.show_error("Fehler beim Speichern", str(e))
            return False

    def load_tuning_config(self):
        """Load tuning settings from config file"""
        config = {}
        config_path = "/etc/bosgame-fan-control.conf"
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    for line in f:
                        if "=" in line and not line.strip().startswith("#"):
                            key, val = line.strip().split("=", 1)
                            config[key] = val.strip('"')
            except:
                pass
        return config

    def show_error(self, title, message):
        """Show error dialog"""
        dialog = Adw.AlertDialog(heading=title, body=message)
        dialog.add_response("ok", "OK")
        dialog.present(self)

    def create_temp_card(self):
        """Create temperature display card with all sensors"""
        card = Adw.PreferencesGroup()
        card.set_title("Temperaturen")

        temp_labels = {}

        for sensor in TEMP_SENSORS:
            if os.path.exists(sensor["path"]):
                row = Adw.ActionRow()
                row.set_title(sensor["name"])

                label = Gtk.Label(label="--°C")
                label.add_css_class("title-4")
                row.add_suffix(label)

                card.add(row)
                temp_labels[sensor["path"]] = {"label": label, "divisor": sensor["divisor"]}

        return card, temp_labels

    def create_power_display_card(self):
        """Create power display card"""
        card = Adw.PreferencesGroup()
        card.set_title("Leistung")

        power_labels = {}

        for sensor in POWER_SENSORS:
            if os.path.exists(sensor["path"]):
                row = Adw.ActionRow()
                row.set_title(sensor["name"])

                label = Gtk.Label(label="--W")
                label.add_css_class("title-4")
                row.add_suffix(label)

                card.add(row)
                power_labels[sensor["path"]] = {"label": label, "divisor": sensor["divisor"]}

        return card, power_labels

    def create_fan_card(self, fan_id, fan_name):
        """Create a fan control card"""
        card = Adw.PreferencesGroup()
        card.set_title(fan_name)

        # RPM and Mode in one row
        rpm_row = Adw.ActionRow()
        rpm_row.set_title("RPM")
        rpm_label = Gtk.Label(label="--")
        rpm_label.add_css_class("title-3")
        rpm_row.add_suffix(rpm_label)
        card.add(rpm_row)

        # Mode row
        mode_row = Adw.ComboRow()
        mode_row.set_title("Modus")
        modes = Gtk.StringList.new(["auto", "fixed", "curve"])
        mode_row.set_model(modes)
        mode_row.connect("notify::selected", self.on_mode_changed, fan_id)
        card.add(mode_row)

        # Level row with scale
        level_row = Adw.ActionRow()
        level_row.set_title("Level")

        level_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 5, 1)
        level_scale.set_draw_value(True)
        level_scale.set_value_pos(Gtk.PositionType.LEFT)
        level_scale.set_hexpand(True)
        level_scale.set_size_request(120, -1)
        level_scale.set_valign(Gtk.Align.CENTER)
        level_scale.connect("value-changed", self.on_level_changed, fan_id)

        level_row.add_suffix(level_scale)
        card.add(level_row)

        return {
            "widget": card,
            "rpm_label": rpm_label,
            "mode_row": mode_row,
            "level_scale": level_scale
        }

    def create_power_card(self):
        """Create power mode card"""
        card = Adw.PreferencesGroup()
        card.set_title("APU Power Mode")

        mode_row = Adw.ComboRow()
        mode_row.set_title("Modus")
        modes = Gtk.StringList.new(["quiet", "balanced", "performance"])
        mode_row.set_model(modes)
        mode_row.connect("notify::selected", self.on_power_mode_changed)
        card.add(mode_row)

        self.power_mode_row = mode_row
        return card

    def create_curve_card(self):
        """Create curve editor card"""
        card = Adw.PreferencesGroup()
        card.set_title("Lüfterkurven")
        card.set_description("Temp-Schwellen für Level 1-5 (kommagetrennt)")

        # Ramp up row
        rampup_row = Adw.ActionRow()
        rampup_row.set_title("Ramp-Up (°C)")

        self.rampup_entry = Gtk.Entry()
        self.rampup_entry.set_placeholder_text("50,60,70,80,90")
        self.rampup_entry.set_valign(Gtk.Align.CENTER)
        self.rampup_entry.set_width_chars(14)
        rampup_row.add_suffix(self.rampup_entry)
        card.add(rampup_row)

        # Ramp down row
        rampdown_row = Adw.ActionRow()
        rampdown_row.set_title("Ramp-Down (°C)")

        self.rampdown_entry = Gtk.Entry()
        self.rampdown_entry.set_placeholder_text("45,55,65,75,85")
        self.rampdown_entry.set_valign(Gtk.Align.CENTER)
        self.rampdown_entry.set_width_chars(14)
        rampdown_row.add_suffix(self.rampdown_entry)
        card.add(rampdown_row)

        # Apply button
        apply_row = Adw.ActionRow()
        apply_btn = Gtk.Button(label="Anwenden")
        apply_btn.add_css_class("suggested-action")
        apply_btn.set_valign(Gtk.Align.CENTER)
        apply_btn.connect("clicked", self.apply_curves)
        apply_row.add_suffix(apply_btn)
        card.add(apply_row)

        return card

    def create_gpu_card(self):
        """Create GPU performance card"""
        card = Adw.PreferencesGroup()
        card.set_title("GPU Performance")

        # GPU Performance Level
        gpu_row = Adw.ComboRow()
        gpu_row.set_title("Performance Level")
        gpu_row.set_subtitle("auto=dynamisch, high=max Takt")
        levels = Gtk.StringList.new(["auto", "low", "high"])
        gpu_row.set_model(levels)
        gpu_row.connect("notify::selected", self.on_gpu_level_changed)
        card.add(gpu_row)
        self.gpu_level_row = gpu_row

        return card

    def on_gpu_level_changed(self, combo, pspec):
        """Handle GPU performance level change"""
        levels = ["auto", "low", "high"]
        selected = combo.get_selected()
        if selected < len(levels):
            try:
                with open("/sys/class/drm/card1/device/power_dpm_force_performance_level", "w") as f:
                    f.write(levels[selected])
            except PermissionError:
                self.show_error("Keine Berechtigung",
                    "GPU-Einstellung erfordert root.\nFühre aus: sudo chmod 666 /sys/class/drm/card1/device/power_dpm_force_performance_level")
            except Exception as e:
                self.show_error("Fehler", str(e))

    def create_tuning_card(self):
        """Create CPU/GPU tuning card with ryzenadj"""
        card = Adw.PreferencesGroup()
        card.set_title("Power Tuning (ryzenadj)")
        card.set_description("Einstellungen werden bei Neustart zurückgesetzt")

        # STAPM (Sustained Power)
        stapm_row = Adw.ActionRow()
        stapm_row.set_title("STAPM (Sustained)")
        stapm_row.set_subtitle("Dauerhafte TDP")

        self.stapm_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 25, 120, 5)
        self.stapm_scale.set_value(65)
        self.stapm_scale.set_draw_value(True)
        self.stapm_scale.set_value_pos(Gtk.PositionType.LEFT)
        self.stapm_scale.set_size_request(120, -1)
        self.stapm_scale.set_valign(Gtk.Align.CENTER)
        self.stapm_scale.set_format_value_func(lambda scale, val: f"{val:.0f}W")
        stapm_row.add_suffix(self.stapm_scale)
        card.add(stapm_row)

        # Fast Limit (Burst Power)
        fast_row = Adw.ActionRow()
        fast_row.set_title("Fast Limit (Burst)")
        fast_row.set_subtitle("Kurzzeit-Boost")

        self.fast_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 25, 150, 5)
        self.fast_scale.set_value(80)
        self.fast_scale.set_draw_value(True)
        self.fast_scale.set_value_pos(Gtk.PositionType.LEFT)
        self.fast_scale.set_size_request(120, -1)
        self.fast_scale.set_valign(Gtk.Align.CENTER)
        self.fast_scale.set_format_value_func(lambda scale, val: f"{val:.0f}W")
        fast_row.add_suffix(self.fast_scale)
        card.add(fast_row)

        # Slow Limit
        slow_row = Adw.ActionRow()
        slow_row.set_title("Slow Limit")
        slow_row.set_subtitle("Mittelfristige TDP")

        self.slow_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 25, 120, 5)
        self.slow_scale.set_value(65)
        self.slow_scale.set_draw_value(True)
        self.slow_scale.set_value_pos(Gtk.PositionType.LEFT)
        self.slow_scale.set_size_request(120, -1)
        self.slow_scale.set_valign(Gtk.Align.CENTER)
        self.slow_scale.set_format_value_func(lambda scale, val: f"{val:.0f}W")
        slow_row.add_suffix(self.slow_scale)
        card.add(slow_row)

        # Temp Limit
        temp_row = Adw.ActionRow()
        temp_row.set_title("Temp Limit")
        temp_row.set_subtitle("Max CPU Temperatur")

        self.temp_limit_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 80, 100, 1)
        self.temp_limit_scale.set_value(95)
        self.temp_limit_scale.set_draw_value(True)
        self.temp_limit_scale.set_value_pos(Gtk.PositionType.LEFT)
        self.temp_limit_scale.set_size_request(120, -1)
        self.temp_limit_scale.set_valign(Gtk.Align.CENTER)
        self.temp_limit_scale.set_format_value_func(lambda scale, val: f"{val:.0f}°C")
        temp_row.add_suffix(self.temp_limit_scale)
        card.add(temp_row)

        # Curve Optimizer (Undervolting)
        co_row = Adw.ActionRow()
        co_row.set_title("CPU Undervolt (CO)")
        co_row.set_subtitle("Negativ = weniger Spannung")

        self.co_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -30, 10, 1)
        self.co_scale.set_value(0)
        self.co_scale.set_draw_value(True)
        self.co_scale.set_value_pos(Gtk.PositionType.LEFT)
        self.co_scale.set_size_request(120, -1)
        self.co_scale.set_valign(Gtk.Align.CENTER)
        self.co_scale.add_mark(0, Gtk.PositionType.BOTTOM, None)
        co_row.add_suffix(self.co_scale)
        card.add(co_row)

        # iGPU Curve Optimizer
        cogfx_row = Adw.ActionRow()
        cogfx_row.set_title("iGPU Undervolt (CO)")
        cogfx_row.set_subtitle("Negativ = weniger Spannung")

        self.cogfx_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -30, 10, 1)
        self.cogfx_scale.set_value(0)
        self.cogfx_scale.set_draw_value(True)
        self.cogfx_scale.set_value_pos(Gtk.PositionType.LEFT)
        self.cogfx_scale.set_size_request(120, -1)
        self.cogfx_scale.set_valign(Gtk.Align.CENTER)
        self.cogfx_scale.add_mark(0, Gtk.PositionType.BOTTOM, None)
        cogfx_row.add_suffix(self.cogfx_scale)
        card.add(cogfx_row)

        # Save checkbox
        save_row = Adw.ActionRow()
        save_row.set_title("Beim Booten laden")
        save_row.set_subtitle("Einstellungen speichern und automatisch anwenden")

        self.save_tuning_switch = Gtk.Switch()
        self.save_tuning_switch.set_valign(Gtk.Align.CENTER)
        save_row.add_suffix(self.save_tuning_switch)
        save_row.set_activatable_widget(self.save_tuning_switch)
        card.add(save_row)

        # Apply button
        apply_row = Adw.ActionRow()
        apply_btn = Gtk.Button(label="Tuning anwenden")
        apply_btn.add_css_class("suggested-action")
        apply_btn.set_valign(Gtk.Align.CENTER)
        apply_btn.connect("clicked", self.apply_tuning)
        apply_row.add_suffix(apply_btn)
        card.add(apply_row)

        return card

    def apply_tuning(self, button):
        """Apply ryzenadj tuning settings"""
        stapm = int(self.stapm_scale.get_value()) * 1000  # Convert to mW
        fast = int(self.fast_scale.get_value()) * 1000
        slow = int(self.slow_scale.get_value()) * 1000
        temp = int(self.temp_limit_scale.get_value())
        co = int(self.co_scale.get_value())
        cogfx = int(self.cogfx_scale.get_value())

        # Get GPU level
        levels = ["auto", "low", "high"]
        gpu_level = levels[self.gpu_level_row.get_selected()]

        # Build command
        args = [
            f"--stapm-limit={stapm}",
            f"--fast-limit={fast}",
            f"--slow-limit={slow}",
            f"--tctl-temp={temp}",
        ]

        if co != 0:
            args.append(f"--set-coall={co}")

        if cogfx != 0:
            args.append(f"--set-cogfx={cogfx}")

        success = self.run_ryzenadj(*args)

        # Save settings if checkbox is checked
        if success and self.save_tuning_switch.get_active():
            self.save_tuning_config(
                int(self.stapm_scale.get_value()),
                int(self.fast_scale.get_value()),
                int(self.slow_scale.get_value()),
                temp, co, cogfx, gpu_level
            )

    def refresh_all(self, button):
        """Refresh all values"""
        # All temperatures
        for path, info in self.temp_labels.items():
            val = self.read_file(path)
            if val:
                try:
                    temp = int(val) / info["divisor"]
                    info["label"].set_label(f"{temp:.0f}°C")
                except:
                    info["label"].set_label("--°C")

        # Power
        for path, info in self.power_labels.items():
            val = self.read_file(path)
            if val:
                try:
                    power = int(val) / info["divisor"]
                    info["label"].set_label(f"{power:.1f}W")
                except:
                    info["label"].set_label("--W")

        # Fans
        for fan_id, card in self.fan_cards.items():
            rpm = self.read_sysfs(f"{fan_id}/rpm")
            mode = self.read_sysfs(f"{fan_id}/mode")
            level = self.read_sysfs(f"{fan_id}/level")

            if rpm:
                card["rpm_label"].set_label(f"{rpm}")

            if mode:
                modes = ["auto", "fixed", "curve"]
                if mode in modes:
                    card["mode_row"].set_selected(modes.index(mode))

            if level:
                card["level_scale"].set_value(int(level))

        # Power mode
        power_mode = self.read_sysfs("apu/power_mode")
        if power_mode:
            modes = ["quiet", "balanced", "performance"]
            if power_mode in modes:
                self.power_mode_row.set_selected(modes.index(power_mode))

        # Curves
        rampup = self.read_sysfs("fan1/rampup_curve")
        rampdown = self.read_sysfs("fan1/rampdown_curve")
        if rampup:
            self.rampup_entry.set_text(rampup)
        if rampdown:
            self.rampdown_entry.set_text(rampdown)

        # GPU Performance Level
        gpu_level = self.read_file("/sys/class/drm/card1/device/power_dpm_force_performance_level")
        if gpu_level:
            levels = ["auto", "low", "high"]
            if gpu_level in levels:
                self.gpu_level_row.set_selected(levels.index(gpu_level))

        # Load saved tuning settings (only on first load)
        if self.has_ryzenadj and hasattr(self, '_first_load'):
            config = self.load_tuning_config()
            if config.get("STAPM_LIMIT"):
                try:
                    self.stapm_scale.set_value(int(config["STAPM_LIMIT"]))
                    self.save_tuning_switch.set_active(True)
                except: pass
            if config.get("FAST_LIMIT"):
                try: self.fast_scale.set_value(int(config["FAST_LIMIT"]))
                except: pass
            if config.get("SLOW_LIMIT"):
                try: self.slow_scale.set_value(int(config["SLOW_LIMIT"]))
                except: pass
            if config.get("TEMP_LIMIT"):
                try: self.temp_limit_scale.set_value(int(config["TEMP_LIMIT"]))
                except: pass
            if config.get("CPU_CO"):
                try: self.co_scale.set_value(int(config["CPU_CO"]))
                except: pass
            if config.get("GPU_CO"):
                try: self.cogfx_scale.set_value(int(config["GPU_CO"]))
                except: pass
            del self._first_load

        return True

    def auto_refresh(self):
        """Auto-refresh callback - only temps, power and RPM"""
        # All temperatures
        for path, info in self.temp_labels.items():
            val = self.read_file(path)
            if val:
                try:
                    temp = int(val) / info["divisor"]
                    info["label"].set_label(f"{temp:.0f}°C")
                except:
                    pass

        # Power
        for path, info in self.power_labels.items():
            val = self.read_file(path)
            if val:
                try:
                    power = int(val) / info["divisor"]
                    info["label"].set_label(f"{power:.1f}W")
                except:
                    pass

        # Fan RPMs
        for fan_id, card in self.fan_cards.items():
            rpm = self.read_sysfs(f"{fan_id}/rpm")
            if rpm:
                card["rpm_label"].set_label(f"{rpm}")

        return True

    def on_mode_changed(self, combo, pspec, fan_id):
        """Handle mode change"""
        modes = ["auto", "fixed", "curve"]
        selected = combo.get_selected()
        if selected < len(modes):
            self.write_sysfs(f"{fan_id}/mode", modes[selected])

    def on_level_changed(self, scale, fan_id):
        """Handle level change"""
        level = int(scale.get_value())
        self.write_sysfs(f"{fan_id}/level", str(level))

    def on_power_mode_changed(self, combo, pspec):
        """Handle power mode change"""
        modes = ["quiet", "balanced", "performance"]
        selected = combo.get_selected()
        if selected < len(modes):
            self.write_sysfs("apu/power_mode", modes[selected])

    def apply_curves(self, button):
        """Apply curve settings"""
        rampup = self.rampup_entry.get_text().strip()
        rampdown = self.rampdown_entry.get_text().strip()

        success = True
        if rampup:
            for fan_id in ["fan1", "fan2", "fan3"]:
                if not self.write_sysfs(f"{fan_id}/rampup_curve", rampup):
                    success = False

        if rampdown:
            for fan_id in ["fan1", "fan2", "fan3"]:
                if not self.write_sysfs(f"{fan_id}/rampdown_curve", rampdown):
                    success = False

        self.refresh_all(None)

def main():
    if not os.path.exists(SYSFS_BASE):
        print("ERROR: ec_su_axb35 driver not loaded")
        print("Run: sudo modprobe ec_su_axb35")
        return 1

    app = FanControlApp()
    return app.run(None)

if __name__ == "__main__":
    main()
