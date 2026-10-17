# USB reset of the leaders of scripts/ports.sh before a wrapper opens them (sourced, not run).
# In the Parallels VM, once a leader's serial port has been closed, the next open finds no servo
# ("Missing motor IDs") and the kernel logs "xhci_hcd ... not part of TD"; the first open after a
# (re)plug always works, and a USB reset gives that fresh link every time.
# Needs `parallels ALL=(root) NOPASSWD: /usr/bin/usbreset` in /etc/sudoers.d; skipped otherwise.
reset_leaders() {
    sudo -n -l /usr/bin/usbreset >/dev/null 2>&1 || return 0
    local leader dev
    for leader in "$@"; do
        [ -e "$leader" ] || continue
        dev=$(readlink -f "/sys/class/tty/$(basename "$(readlink -f "$leader")")/device/..")
        [ -f "$dev/busnum" ] || continue
        sudo -n /usr/bin/usbreset "$(printf '%03d/%03d' "$(cat "$dev/busnum")" "$(cat "$dev/devnum")")" >/dev/null
    done
    for _ in $(seq 20); do  # wait until every leader port is back
        local missing=0
        for leader in "$@"; do [ -e "$leader" ] || missing=1; done
        [ "$missing" = 0 ] && break
        sleep 0.25
    done
    sleep 0.5
}
