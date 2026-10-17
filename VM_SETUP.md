# VM robot (Ubuntu dans Parallels, Mac Apple Silicon)

Le SDK OpenArm parle au robot via SocketCAN, donc Linux uniquement. Sur Mac M1/M2/M3,
Parallels ne fait tourner que des Linux **ARM64**. Ça tombe bien : le PPA OpenArm publie
des paquets arm64 pour Ubuntu 24.04 (vérifié le 17/10 : `libopenarm-can-dev`,
`openarm-can-utils`, `python3-openarm-can` en version 1.4.0, la même que sur PyPI).

## 0. À demander au coéquipier dont le laptop est branché (5 min, ça évite 1 h de debug)

Sur sa machine : `ip -details link show can0` (et `can1`).
- **CAN-FD ou CAN 2.0 ?** (`fd on` ou non, `bitrate`, `dbitrate`). Les moteurs ne répondent
  qu'au débit pour lequel ils sont configurés.
- **Combien d'interfaces ?** Config OpenArm : bras droit = `can0`, bras gauche = `can1`.
  Il faut les deux pour verser (un bras tient le verre). Avec une seule interface, poser le
  verre sur la table.
- **Quel adaptateur ?** (`lsusb`). candleLight/CANable 2 → `gs_usb` ; PEAK → `peak_usb` ;
  adaptateur série (firmware slcan) → `slcand`, et pas de CAN-FD.
- **Quelle pile pilote le robot ?** openarm_driver en Python, dataflow Dora (stack Enactic),
  ROS 2 ? Ça décide comment `pour` s'intègre (voir README, section Intégration).

## 1. Créer la VM

1. Parallels → Fichier → Nouveau → « Télécharger Ubuntu Linux » (24.04 ARM64), ou une ISO
   `ubuntu-24.04-desktop-arm64.iso`.
2. Configuration : 4 vCPU, 8 Go de RAM, 40 Go de disque.
3. Installer les Parallels Tools (menu Actions). Ils donnent le **dossier partagé** : ton home
   Mac est visible dans la VM sous `/media/psf/Home`. Tu édites sur le Mac, tu lances dans la
   VM, sans aller-retour git.

## 2. Rediriger l'adaptateur USB-CAN vers la VM

- VM au premier plan → menu **Périphériques → USB et Bluetooth →** cliquer l'adaptateur.
  Il est déconnecté du Mac et branché dans la VM.
- Pour que ce soit automatique : Configuration de la VM → Matériel → USB et Bluetooth, ou
  Réglages Parallels → Périphériques : associer l'adaptateur à la VM.
- Vérifier dans la VM :
  ```bash
  lsusb                    # l'adaptateur apparaît
  sudo dmesg | tail -20    # gs_usb / peak_usb a créé can0
  ip link                  # can0 (et can1)
  ```
- Webcam du verre : même menu, ou « Partager la caméra du Mac » (la caméra du Mac
  apparaît dans la VM en `/dev/video0`).

## 3. Installer

```bash
cd /media/psf/Home/pour_skill        # ou : git clone <repo> ~/pour_skill && cd ~/pour_skill
./setup_robot_vm.sh                  # CAN-FD 1M/5M (défaut OpenArm)
./setup_robot_vm.sh --no-fd          # si le coéquipier est en CAN 2.0
```
Le script installe dans l'ordre : paquets de base, PPA OpenArm (et compile depuis les sources
si le PPA échoue), modules noyau CAN, venv `~/venvs/pour` (avec `--system-site-packages`
pour réutiliser `python3-openarm-can` d'apt), `openarm-driver`, puis configure `can0`/`can1`.
Il n'envoie aucune commande moteur.

Garder le venv **dans la VM** (`~/venvs/pour`), pas dans le dossier partagé : les binaires
macOS du `.venv` local ne marchent pas sous Linux.

## 4. Tester, du plus sûr au moins sûr

| # | Commande | Envoie des trames ? | Risque |
|---|---|---|---|
| 1 | `candump -t d can0` | non | aucun |
| 2 | `python log_torque.py --backend sniff --duration 20` | non | aucun |
| 3 | `python vendor/openarm_driver/samples/health_check.py right_arm` ou `python log_torque.py --backend openarm --duration 5` | lecture seule (`refresh`) | aucun mouvement ; moteurs non armés, couple ~0 |
| 4 | `python log_torque.py --backend openarm --hold --i-understand-motors-will-be-armed` | oui | arme le bras et tient la pose actuelle. Soutenir le bras au démarrage |
| 5 | `python pour_skill.py --backend openarm --sensor camera --i-understand-motors-will-be-armed` | oui | le bras bouge. Main sur l'arrêt d'urgence |

1 et 2 ne voient rien si personne ne pilote les moteurs : c'est normal, on n'écoute que leurs réponses.

**Attention à `openarm-can-cli -i can0 monitor`** (lu dans le code source) :
- il **arme** tous les moteurs au démarrage et les **désarme** à la fin : un bras en l'air
  tombe, une pince lâche ce qu'elle tient ;
- il suppose que les 8 moteurs sont des DM4310 : les couples affichés pour J1-J2 (DM8009)
  sont à multiplier par 5.4, ceux de J3-J4 (DM4340) par 2.8. Les vitesses aussi sont fausses.
- Ne jamais le lancer pendant que quelqu'un d'autre pilote le bras. Préférer le test 2.

## 5. Cas : on utilise la machine du coéquipier (déjà branchée)

Rien à installer côté OpenArm, il l'a déjà. Sur sa machine (ou sa VM) :
```bash
git clone <repo> ~/pour_skill && cd ~/pour_skill
python3 -m venv --system-site-packages ~/venvs/pour && source ~/venvs/pour/bin/activate
pip install numpy pandas matplotlib opencv-python
python log_torque.py --backend sniff --arm right_arm --duration 0 --label teleop   # Ctrl+C pour finir
```
Le backend `sniff` n'envoie **rien** sur le bus : on peut le lancer **pendant sa téléop**
sans aucun risque. On récupère positions et couples de chaque épisode **sans consommer de
temps robot**. C'est aussi le moyen de relever les poses (`approach_pose`, angle de la
bouteille verticale, sens de basculement) à mettre dans `PourConfig`.

## 6. Dépannage

- `ip link` ne montre pas `can0` : adaptateur pas redirigé (étape 2), module absent
  (`sudo modprobe gs_usb`), ou adaptateur série (`slcand`).
- `can0` passe en `BUS-OFF` / `ERROR-PASSIVE` : mauvais débit ou mauvais mode FD
  (`ip -details -statistics link show can0`), terminaison 120 Ω manquante, ou deux
  programmes qui commandent le même bras.
- Moteurs muets mais bus OK : alimentation 24 V coupée ou arrêt d'urgence enfoncé.
- Gigue USB dans la VM : rester vers 100 Hz de commande (c'est le défaut de `Robot`).
  Si des trames se perdent, regarder les compteurs `ip -s link show can0`.

## 7. Tout piloter depuis le Mac (ssh robotvm)

**Une fois, dans le terminal de la VM** (la clé publique est celle générée sur le Mac,
`~/.ssh/id_ed25519_robotvm.pub`) :
```bash
sudo apt update && sudo apt install -y openssh-server rsync
sudo systemctl enable --now ssh
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo '<contenu de ~/.ssh/id_ed25519_robotvm.pub du Mac>' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
echo "USER=$(whoami)  IP=$(hostname -I)"
```
L'IP du réseau partagé Parallels ressemble à 10.211.55.x. Avec les Parallels Tools,
`prlctl list -a -o name,ip` la donne aussi depuis le Mac.

**Sur le Mac** :
```bash
./sync_to_vm.sh --configure <user> <ip>     # renseigne l'alias robotvm (~/.ssh/config)
ssh robotvm true && echo OK                  # test de connexion
./sync_to_vm.sh --setup                      # 1re fois : installe tout (mot de passe sudo de la VM)
./run_on_vm.sh tests/sniff_selftest.py --iface vcan0           # sniff sur bus virtuel
./run_on_vm.sh log_torque.py --backend sniff --duration 20     # sniff sur le vrai bus
```
- `sync_to_vm.sh` fait un rsync vers `~/pour_skill`, sans `.venv`, `vendor`, `.git`, ni les
  dossiers produits sur la VM (`data`, `plots`, `config`, `state`). Il lance le setup si le venv
  est absent.
- `run_on_vm.sh <script> [args]` synchronise, exécute le script dans `~/venvs/pour`, affiche la
  sortie en direct (Ctrl+C transmis), puis rapatrie `data/ plots/ config/ state/` dans
  `./results/`. `./run_on_vm.sh -- <commande>` lance une commande arbitraire.
- **Garde-fou** : `--i-understand-motors-will-be-armed`, `--hold`, ou une commande
  `openarm-can-cli monitor/enable/...` demandent de taper `OUI`. Sans terminal interactif, c'est
  refusé.
- Les fenêtres OpenCV (`glass_level.py --calibrate`) s'ouvrent sur l'écran de la VM (`DISPLAY=:0`).
  Si rien ne s'affiche (session Wayland), lancer la calibration directement dans le terminal de la VM.
