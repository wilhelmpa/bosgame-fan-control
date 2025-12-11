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
        self.set_default_size(500, 950)

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

        # Ryzenadj tuning card (if available)
        if self.has_ryzenadj:
            self.tuning_card = self.create_tuning_card()
            content.append(self.tuning_card)

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
        """Run ryzenadj with pkexec"""
        try:
            cmd = ["pkexec", "ryzenadj"] + list(args)
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

    def create_tuning_card(self):
        """Create CPU/GPU tuning card with ryzenadj"""
        card = Adw.PreferencesGroup()
        card.set_title("Power Tuning (ryzenadj)")
        card.set_description("Einstellungen werden bei Neustart zurückgesetzt")

        # Power Limit (STAPM)
        power_row = Adw.ActionRow()
        power_row.set_title("Power Limit (TDP)")
        power_row.set_subtitle("25-120W")

        power_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        power_box.set_valign(Gtk.Align.CENTER)

        self.power_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 25, 120, 5)
        self.power_scale.set_value(65)
        self.power_scale.set_draw_value(True)
        self.power_scale.set_value_pos(Gtk.PositionType.LEFT)
        self.power_scale.set_size_request(100, -1)
        self.power_scale.set_format_value_func(lambda scale, val: f"{val:.0f}W")
        power_box.append(self.power_scale)

        power_row.add_suffix(power_box)
        card.add(power_row)

        # Temp Limit
        temp_row = Adw.ActionRow()
        temp_row.set_title("Temp Limit")
        temp_row.set_subtitle("80-100°C")

        temp_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        temp_box.set_valign(Gtk.Align.CENTER)

        self.temp_limit_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 80, 100, 1)
        self.temp_limit_scale.set_value(95)
        self.temp_limit_scale.set_draw_value(True)
        self.temp_limit_scale.set_value_pos(Gtk.PositionType.LEFT)
        self.temp_limit_scale.set_size_request(100, -1)
        self.temp_limit_scale.set_format_value_func(lambda scale, val: f"{val:.0f}°C")
        temp_box.append(self.temp_limit_scale)

        temp_row.add_suffix(temp_box)
        card.add(temp_row)

        # Curve Optimizer (Undervolting)
        co_row = Adw.ActionRow()
        co_row.set_title("CPU Undervolt")
        co_row.set_subtitle("-30 bis +10 (negativ = weniger Spannung)")

        co_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        co_box.set_valign(Gtk.Align.CENTER)

        self.co_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -30, 10, 1)
        self.co_scale.set_value(0)
        self.co_scale.set_draw_value(True)
        self.co_scale.set_value_pos(Gtk.PositionType.LEFT)
        self.co_scale.set_size_request(100, -1)
        self.co_scale.add_mark(0, Gtk.PositionType.BOTTOM, "0")
        self.co_scale.add_mark(-15, Gtk.PositionType.BOTTOM, "-15")
        co_box.append(self.co_scale)

        co_row.add_suffix(co_box)
        card.add(co_row)

        # iGPU Curve Optimizer
        cogfx_row = Adw.ActionRow()
        cogfx_row.set_title("iGPU Undervolt")
        cogfx_row.set_subtitle("-30 bis +10")

        cogfx_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cogfx_box.set_valign(Gtk.Align.CENTER)

        self.cogfx_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -30, 10, 1)
        self.cogfx_scale.set_value(0)
        self.cogfx_scale.set_draw_value(True)
        self.cogfx_scale.set_value_pos(Gtk.PositionType.LEFT)
        self.cogfx_scale.set_size_request(100, -1)
        cogfx_box.append(self.cogfx_scale)

        cogfx_row.add_suffix(cogfx_box)
        card.add(cogfx_row)

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
        power = int(self.power_scale.get_value()) * 1000  # Convert to mW
        temp = int(self.temp_limit_scale.get_value())
        co = int(self.co_scale.get_value())
        cogfx = int(self.cogfx_scale.get_value())

        # Build command
        args = [
            f"--stapm-limit={power}",
            f"--fast-limit={power}",
            f"--slow-limit={power}",
            f"--tctl-temp={temp}",
        ]

        if co != 0:
            args.append(f"--set-coall={co}")

        if cogfx != 0:
            args.append(f"--set-cogfx={cogfx}")

        self.run_ryzenadj(*args)

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

        return True

    def auto_refresh(self):
        """Auto-refresh callback - only temps and RPM"""
        # All temperatures
        for path, info in self.temp_labels.items():
            val = self.read_file(path)
            if val:
                try:
                    temp = int(val) / info["divisor"]
                    info["label"].set_label(f"{temp:.0f}°C")
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
