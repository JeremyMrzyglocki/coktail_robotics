#!/usr/bin/env bash
# Bring can0/can1 up as CAN FD 1 Mbps / 5 Mbps, sample point 0.75 (needed after every VM reboot or
# PCAN replug). Sends nothing on the bus. Usage: ./scripts/setup_can.sh
set -e
for i in can0 can1; do
    if ! ip link show "$i" >/dev/null 2>&1; then
        echo "$i missing: is the PCAN-USB Pro FD passed through to the VM? (lsusb | grep -i peak)"
        exit 1
    fi
    sudo ip link set "$i" down
    sudo ip link set "$i" type can bitrate 1000000 sample-point 0.75 dbitrate 5000000 dsample-point 0.75 \
        fd on restart-ms 100
    sudo ip link set "$i" up
    ip -details link show "$i" | grep -oE 'state [A-Z-]+ \(berr|can <FD> state [A-Z-]+' | head -1 | sed "s/^/$i: /"
done
