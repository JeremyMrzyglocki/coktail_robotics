#!/usr/bin/env bash
# Installe l'environnement robot sur Ubuntu 24.04 (VM Parallels ARM64 ou machine Linux).
# Ne fait JAMAIS bouger le robot : aucune commande moteur n'est envoyée.
#
#   ./setup_robot_vm.sh                       # tout, CAN-FD 1M/5M (défaut OpenArm)
#   ./setup_robot_vm.sh --no-fd               # CAN 2.0 à 1 Mbit/s
#   ./setup_robot_vm.sh --skip-can            # sans toucher aux interfaces CAN
#   ./setup_robot_vm.sh --project /media/psf/Home/pour_skill --venv ~/venvs/pour
#
# AVANT de configurer le CAN : vérifier avec le coéquipier qui pilote déjà le
# robot le mode utilisé (ip -details link show can0 sur sa machine). Les
# moteurs ne répondent qu'au débit pour lequel ils sont configurés.

set -euo pipefail

FD=1
SKIP_CAN=0
PROJECT="${HOME}/pour_skill"
[ -d /media/psf/Home/pour_skill ] && PROJECT=/media/psf/Home/pour_skill   # dossier partagé Parallels
VENV="${HOME}/venvs/pour"
IFACES=(can0 can1)

while [ $# -gt 0 ]; do
  case "$1" in
    --no-fd) FD=0 ;;
    --skip-can) SKIP_CAN=1 ;;
    --project) PROJECT="$2"; shift ;;
    --venv) VENV="$2"; shift ;;
    --ifaces) IFS=, read -r -a IFACES <<< "$2"; shift ;;
    -h|--help) sed -n 2,14p "$0"; exit 0 ;;
    *) echo "option inconnue : $1"; exit 1 ;;
  esac
  shift
done

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }

say "Système : $(. /etc/os-release && echo "$PRETTY_NAME") / $(uname -m) / noyau $(uname -r)"
. /etc/os-release
[ "${VERSION_ID}" = "24.04" ] || warn "Testé pour Ubuntu 24.04 ; le PPA couvre aussi 22.04 et 26.04."

say "Paquets de base"
sudo apt-get update
sudo apt-get install -y software-properties-common git curl can-utils iproute2 usbutils \
  python3-venv python3-dev python3-pip build-essential cmake pkg-config

say "Paquets OpenArm (ppa:openarm/main, arm64 et amd64 disponibles)"
if sudo add-apt-repository -y ppa:openarm/main && sudo apt-get update \
   && sudo apt-get install -y libopenarm-can-dev openarm-can-utils python3-openarm-can; then
  OPENARM_FROM=ppa
else
  warn "PPA indisponible : compilation depuis les sources."
  OPENARM_FROM=source
  SRC="${HOME}/src/openarm_can"
  [ -d "$SRC" ] || git clone --depth 1 https://github.com/enactic/openarm_can.git "$SRC"
  cmake -S "$SRC" -B "$SRC/build" -DCMAKE_BUILD_TYPE=Release
  cmake --build "$SRC/build" -j"$(nproc)"
  sudo cmake --install "$SRC/build"
  sudo ldconfig
fi

say "Modules noyau CAN"
if ! sudo modprobe can_raw 2>/dev/null; then
  warn "can_raw absent : installation de linux-modules-extra-$(uname -r)"
  sudo apt-get install -y "linux-modules-extra-$(uname -r)" && sudo modprobe can_raw
fi
sudo modprobe can || true
sudo modprobe can_dev || true
for m in gs_usb peak_usb kvaser_usb slcan; do   # candleLight/CANable, PEAK, Kvaser, série
  sudo modprobe "$m" 2>/dev/null || true
done
lsmod | grep -E '^(can|can_raw|can_dev|gs_usb|peak_usb|slcan)\b' || true

say "Environnement Python : $VENV"
mkdir -p "$(dirname "$VENV")"
# --system-site-packages : pour réutiliser python3-openarm-can installé par apt
[ -d "$VENV" ] || python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q numpy pandas matplotlib opencv-python pyyaml
if [ "$OPENARM_FROM" = source ]; then
  "$VENV/bin/pip" install -q "$HOME/src/openarm_can/python"
fi
"$VENV/bin/pip" install -q --no-deps openarm-driver
"$VENV/bin/python" - <<'EOF'
import openarm_can, openarm_driver
print("openarm_can   :", openarm_can.__file__)
print("openarm_driver:", openarm_driver.__file__, openarm_driver.available_configs())
EOF

say "Projet : $PROJECT"
if [ ! -d "$PROJECT" ]; then
  warn "Projet introuvable. Soit le dossier partagé Parallels (/media/psf/Home/pour_skill),"
  warn "soit : git clone <url-du-repo> $PROJECT"
fi

if [ "$SKIP_CAN" = 0 ]; then
  say "Interfaces CAN (FD=$FD)"
  found=0
  for IF in "${IFACES[@]}"; do
    if ip link show "$IF" &>/dev/null; then
      found=1
      sudo ip link set "$IF" down
      if [ "$FD" = 1 ]; then
        sudo ip link set "$IF" type can bitrate 1000000 dbitrate 5000000 fd on
      else
        sudo ip link set "$IF" type can bitrate 1000000
      fi
      sudo ip link set "$IF" txqueuelen 1000 up
      ip -details -statistics link show "$IF" | sed -n '1,8p'
    else
      warn "$IF absente"
    fi
  done
  if [ "$found" = 0 ]; then
    warn "Aucune interface CAN. Adaptateur bien connecté à la VM (menu Parallels Périphériques > USB) ?"
    warn "lsusb ; sudo dmesg | tail -30 ; ip link"
    warn "Adaptateur série (slcan) : sudo slcand -o -c -s8 /dev/ttyACM0 can0 && sudo ip link set can0 up  (pas de CAN-FD)"
  fi
fi

say "Terminé. Tests SANS RISQUE (aucune trame moteur envoyée) :"
cat <<EOF
  candump -t d can0                      # trafic brut (vide si personne ne pilote)
  source $VENV/bin/activate && cd $PROJECT
  python log_torque.py --backend sniff --duration 20     # écoute passive + couples décodés

Test qui interroge les moteurs (trames de lecture, moteurs NON armés) :
  python log_torque.py --backend openarm --duration 5

ATTENTION 'openarm-can-cli -i can0 monitor' : il ARME les moteurs au début et les
DÉSARME à la fin (le bras tombe s'il est en l'air), et il suppose des DM4310 :
couple affiché J1-J2 à multiplier par 5.4, J3-J4 par 2.8. À éviter si quelqu'un
d'autre pilote le bras.
EOF
