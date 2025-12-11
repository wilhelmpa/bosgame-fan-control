#!/bin/bash
# Bosgame M5 Fan Control - Apply configuration
# This script is called by systemd to apply fan settings at boot

SYSFS_BASE="/sys/class/ec_su_axb35"
CONFIG_FILE="/etc/bosgame-fan-control.conf"

# Wait for driver to be loaded
wait_for_driver() {
    local count=0
    while [ ! -d "$SYSFS_BASE" ] && [ $count -lt 30 ]; do
        sleep 1
        count=$((count + 1))
    done

    if [ ! -d "$SYSFS_BASE" ]; then
        echo "ERROR: Driver not loaded after 30 seconds"
        exit 1
    fi
}

# Load configuration
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        source "$CONFIG_FILE"
    else
        echo "WARNING: Config file not found, using defaults"
        POWER_MODE="balanced"
        FAN_MODE="auto"
        RAMPUP_CURVE="50 60 70 80 90"
        RAMPDOWN_CURVE="45 55 65 75 85"
    fi
}

# Set permissions for user access
set_permissions() {
    echo "Setting permissions for user access..."
    for fan in fan1 fan2 fan3; do
        chmod 666 "$SYSFS_BASE/$fan/mode" 2>/dev/null
        chmod 666 "$SYSFS_BASE/$fan/level" 2>/dev/null
        chmod 666 "$SYSFS_BASE/$fan/rampup_curve" 2>/dev/null
        chmod 666 "$SYSFS_BASE/$fan/rampdown_curve" 2>/dev/null
    done
    chmod 666 "$SYSFS_BASE/apu/power_mode" 2>/dev/null

    # GPU performance level control
    chmod 666 /sys/class/drm/card1/device/power_dpm_force_performance_level 2>/dev/null

    echo "  Permissions set"
}

# Apply settings
apply_settings() {
    echo "Applying Bosgame M5 fan control settings..."

    # Power mode
    if [ -n "$POWER_MODE" ]; then
        echo "$POWER_MODE" > "$SYSFS_BASE/apu/power_mode"
        echo "  Power mode: $POWER_MODE"
    fi

    # Apply to all fans
    for fan in fan1 fan2 fan3; do
        if [ -d "$SYSFS_BASE/$fan" ]; then
            # Fan mode
            if [ -n "$FAN_MODE" ]; then
                echo "$FAN_MODE" > "$SYSFS_BASE/$fan/mode"
            fi

            # Curves (only if mode is curve)
            if [ "$FAN_MODE" = "curve" ]; then
                if [ -n "$RAMPUP_CURVE" ]; then
                    echo "$RAMPUP_CURVE" > "$SYSFS_BASE/$fan/rampup_curve"
                fi
                if [ -n "$RAMPDOWN_CURVE" ]; then
                    echo "$RAMPDOWN_CURVE" > "$SYSFS_BASE/$fan/rampdown_curve"
                fi
            fi

            echo "  $fan: mode=$FAN_MODE"
        fi
    done

    echo "Fan control settings applied successfully"
}

# Apply ryzenadj tuning settings
apply_tuning() {
    if [ -z "$STAPM_LIMIT" ]; then
        echo "No tuning settings found, skipping ryzenadj"
        return
    fi

    echo "Applying ryzenadj tuning settings..."

    # Build ryzenadj command
    RYZENADJ_ARGS=""

    if [ -n "$STAPM_LIMIT" ]; then
        STAPM_MW=$((STAPM_LIMIT * 1000))
        RYZENADJ_ARGS="$RYZENADJ_ARGS --stapm-limit=$STAPM_MW"
    fi

    if [ -n "$FAST_LIMIT" ]; then
        FAST_MW=$((FAST_LIMIT * 1000))
        RYZENADJ_ARGS="$RYZENADJ_ARGS --fast-limit=$FAST_MW"
    fi

    if [ -n "$SLOW_LIMIT" ]; then
        SLOW_MW=$((SLOW_LIMIT * 1000))
        RYZENADJ_ARGS="$RYZENADJ_ARGS --slow-limit=$SLOW_MW"
    fi

    if [ -n "$TEMP_LIMIT" ]; then
        RYZENADJ_ARGS="$RYZENADJ_ARGS --tctl-temp=$TEMP_LIMIT"
    fi

    if [ -n "$CPU_CO" ] && [ "$CPU_CO" != "0" ]; then
        RYZENADJ_ARGS="$RYZENADJ_ARGS --set-coall=$CPU_CO"
    fi

    if [ -n "$GPU_CO" ] && [ "$GPU_CO" != "0" ]; then
        RYZENADJ_ARGS="$RYZENADJ_ARGS --set-cogfx=$GPU_CO"
    fi

    if [ -n "$RYZENADJ_ARGS" ]; then
        echo "  Running: ryzenadj $RYZENADJ_ARGS"
        /usr/bin/ryzenadj $RYZENADJ_ARGS 2>&1 | grep -v "no compatible"
    fi

    # GPU Performance Level
    if [ -n "$GPU_LEVEL" ]; then
        echo "$GPU_LEVEL" > /sys/class/drm/card1/device/power_dpm_force_performance_level 2>/dev/null
        echo "  GPU Performance Level: $GPU_LEVEL"
    fi

    echo "Tuning settings applied"
}

# Main
case "$1" in
    start)
        wait_for_driver
        set_permissions
        load_config
        apply_settings
        apply_tuning
        ;;
    status)
        if [ -d "$SYSFS_BASE" ]; then
            echo "Driver: loaded"
            echo "Temperature: $(cat $SYSFS_BASE/temp1/temp)°C"
            for fan in fan1 fan2 fan3; do
                echo "$fan: $(cat $SYSFS_BASE/$fan/rpm) RPM, mode=$(cat $SYSFS_BASE/$fan/mode)"
            done
            echo "Power mode: $(cat $SYSFS_BASE/apu/power_mode)"
        else
            echo "Driver: not loaded"
        fi
        ;;
    *)
        echo "Usage: $0 {start|status}"
        exit 1
        ;;
esac
