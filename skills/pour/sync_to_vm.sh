#!/usr/bin/env bash
# Synchronise le projet du Mac vers la VM robot (~/pour_skill), puis installe si besoin.
#
#   ./sync_to_vm.sh                       # rsync + setup si le venv de la VM n'existe pas
#   ./sync_to_vm.sh --setup               # rsync + (ré)exécute setup_robot_vm.sh (demande le mot de passe sudo)
#   ./sync_to_vm.sh --no-setup --quiet    # rsync seul (utilisé par run_on_vm.sh)
#   ./sync_to_vm.sh --configure <user> <ip>   # renseigne l'alias robotvm dans ~/.ssh/config
#
# Exclus : .venv, vendor, .git, data/plots/results, et config/ + state/ : les calibrations
# (caméra, couple) et l'état du bar sont PRODUITS sur la VM ; on ne les écrase jamais depuis
# le Mac. run_on_vm.sh les rapatrie dans ./results/.
# Options setup supplémentaires : SETUP_ARGS="--no-fd" ./sync_to_vm.sh --setup

set -euo pipefail
cd "$(dirname "$0")"
HOST="${ROBOTVM:-robotvm}"
REMOTE_DIR="pour_skill"
VENV_PY='~/venvs/pour/bin/python'
SETUP=auto
QUIET=0

while [ $# -gt 0 ]; do
  case "$1" in
    --setup) SETUP=yes ;;
    --no-setup) SETUP=no ;;
    --quiet) QUIET=1 ;;
    --configure)
      [ $# -ge 3 ] || { echo "usage : $0 --configure <user> <ip>"; exit 1; }
      sed -i '' -e "/^Host robotvm$/,/^# --- fin pour-skill/ s/^\(    HostName \).*/\1$3/" \
                -e "/^Host robotvm$/,/^# --- fin pour-skill/ s/^\(    User \).*/\1$2/" ~/.ssh/config
      sed -n '/^Host robotvm$/,/^# --- fin pour-skill/p' ~/.ssh/config
      exit 0 ;;
    -h|--help) sed -n 2,14p "$0"; exit 0 ;;
    *) echo "option inconnue : $1"; exit 1 ;;
  esac
  shift
done

log() { [ "$QUIET" = 1 ] || printf '\033[1;34m==> %s\033[0m\n' "$*"; }

if grep -A2 '^Host robotvm$' ~/.ssh/config 2>/dev/null | grep -q CHANGE_ME && [ "$HOST" = robotvm ]; then
  echo "Alias robotvm pas encore configuré : ./sync_to_vm.sh --configure <user> <ip>" >&2
  exit 1
fi
if ! ssh -o BatchMode=yes "$HOST" true 2>/dev/null; then
  echo "SSH vers $HOST impossible (VM allumée ? IP changée ? clé ajoutée ?). Test : ssh -v $HOST" >&2
  exit 1
fi

log "rsync -> $HOST:~/$REMOTE_DIR"
rsync -az --delete \
  --exclude '.venv/' --exclude 'vendor/' --exclude '.git/' --exclude '__pycache__/' \
  --exclude '.DS_Store' --exclude 'data/' --exclude 'plots/' --exclude 'results/' \
  --exclude 'config/' --exclude 'state/' \
  ./ "$HOST:$REMOTE_DIR/"

if [ "$SETUP" = auto ]; then
  if ssh "$HOST" "$VENV_PY -c 'import numpy, cv2, yaml, openarm_driver'" 2>/dev/null; then
    SETUP=no
  else
    SETUP=yes
    log "venv absent ou incomplet sur la VM : lancement de setup_robot_vm.sh"
  fi
fi
if [ "$SETUP" = yes ]; then
  if [ ! -t 0 ]; then
    echo "setup_robot_vm.sh demande le mot de passe sudo : lancer ./sync_to_vm.sh --setup dans un terminal." >&2
    exit 2
  fi
  ssh -t "$HOST" "cd ~/$REMOTE_DIR && ./setup_robot_vm.sh --project ~/$REMOTE_DIR ${SETUP_ARGS:-}"
fi
log "OK"
