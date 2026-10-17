#!/usr/bin/env bash
# Lance un script du projet dans la VM robot, depuis le Mac, sortie en direct.
#
#   ./run_on_vm.sh log_torque.py --backend sniff --duration 20
#   ./run_on_vm.sh pour_skill.py --backend mock --container red --grams 60
#   ./run_on_vm.sh -- bash -lc 'ip -details link show can0'     # commande arbitraire
#
# Étapes : sync (sync_to_vm.sh --no-setup) -> exécution dans ~/venvs/pour sur la VM (Ctrl+C
# est transmis au script distant, qui redresse la bouteille) -> rapatriement de data/, plots/,
# config/ et state/ de la VM dans ./results/ (jamais de suppression côté Mac).
#
# GARDE-FOU : si les arguments arment les moteurs (--i-understand-motors-will-be-armed, --hold,
# ou en mode "--" : openarm-can-cli monitor/enable/set_zero/..., cansend),
# confirmation "OUI" demandée au clavier. Non interactif => refus, sauf ROBOT_MOTORS_OK=1.
# Fenêtres OpenCV (calibration) : elles s'ouvrent sur l'écran de la VM (DISPLAY=:0).

set -uo pipefail
cd "$(dirname "$0")"
HOST="${ROBOTVM:-robotvm}"
REMOTE_DIR="pour_skill"

[ $# -ge 1 ] || { sed -n 2,16p "$0"; exit 1; }

MOTOR_ARGS='^--(i-understand-motors-will-be-armed|hold)$'
MOTOR_CLI='openarm-can-cli.*(monitor|enable|set_zero|write_param|change_id|change_baud)|cansend'
if printf '%s\n' "$@" | grep -qE -- "$MOTOR_ARGS" || { [ "$1" = "--" ] && printf '%s ' "$@" | grep -qE "$MOTOR_CLI"; }; then
  if [ "${ROBOT_MOTORS_OK:-}" != 1 ]; then
    if [ ! -t 0 ]; then
      echo "REFUSÉ : commande moteur sans confirmation interactive (ROBOT_MOTORS_OK=1 pour forcer)." >&2
      exit 3
    fi
    printf '\033[1;31m⚠ Cette commande ARME les moteurs du vrai robot.\033[0m\n'
    read -r -p "Arrêt d'urgence à portée de main ? Taper OUI pour continuer : " ans
    [ "$ans" = "OUI" ] || { echo "annulé"; exit 3; }
  fi
fi

./sync_to_vm.sh --no-setup --quiet || exit $?

if [ "$1" = "--" ]; then
  shift
  CMD="cd ~/$REMOTE_DIR && $(printf '%q ' "$@")"
else
  CMD="cd ~/$REMOTE_DIR && DISPLAY=\${DISPLAY:-:0} ~/venvs/pour/bin/python -u $(printf '%q ' "$@")"
fi
if [ -t 0 ]; then TTY=-t; else TTY=-T; fi

ssh $TTY "$HOST" "$CMD"
rc=$?

mkdir -p results
for d in data plots config state; do
  rsync -az "$HOST:$REMOTE_DIR/$d/" "results/$d/" 2>/dev/null || true
done
printf '\033[1;34m==> code retour %s ; résultats rapatriés dans ./results/\033[0m\n' "$rc"
exit $rc
