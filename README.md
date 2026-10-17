# pour_skill : skill « verser » pour OpenArm (ERH Physical AI Hackathon, track Daidai)

Un bras tient le verre, l'autre la bouteille de riz (ou de bonbons) et verse en boucle fermée :
la vision mesure le niveau dans le verre, et le couple moteur sert en option à peser la bouteille.

```
robot_io.py             Robot partagé : backends mock / openarm / sniff (écoute CAN passive)
pour_skill.py           pour(robot, target_amount, ...) : machine à états, timeouts, retour sûr
glass_level.py          niveau du verre par webcam (HSV ou différence avec le verre vide), calibration
log_torque.py           log CSV des couples, lecture seule par défaut
analyze_torque.py       bruit, régression masse -> couple, figures pour les slides
orchestrator_example.py une connexion, pick & place (stub de la policy GPU) puis pour
VM_SETUP.md / setup_robot_vm.sh   Ubuntu ARM64 dans Parallels, PPA OpenArm, USB-CAN, SocketCAN
```

## Démarrage (Mac, mock)

```bash
source .venv/bin/activate
python pour_skill.py --backend mock --target 0.5 --torque      # versement simulé
python orchestrator_example.py --prompt "je veux un barman"     # pick & place + pour
python analyze_torque.py --demo                                 # pesées simulées -> plots/
python analyze_torque.py --pour data/pour_<...>.csv             # figure d'un versement
python glass_level.py --selftest && python glass_level.py --calibrate   # webcam
python tests/test_basics.py
```

## Ce que dit le SDK (lu dans `vendor/`)

**Noms et interfaces.** Les bras s'appellent `"right_arm"` et `"left_arm"`. Chaque bras a son
interface CAN : `can0` pour le droit, `can1` pour le gauche (`openarm_cell.yaml`). Un bras compte
8 moteurs : J1-J7 plus la pince J8. Identifiants d'envoi 0x01-0x08, de réponse 0x11-0x18.
Types : DM8009 pour J1-J2, DM4340 pour J3-J4, DM4310 pour J5-J8.

**Lire le couple.** `SingleArmDriver.fetch_state()` renvoie `qpos`, `qvel`, `qtorque`, `tmos`
et `trotor` (aussi `fetch_torque()`). Le couple est une **estimation à partir du courant** (pas
un capteur), codée sur **12 bits dans ±tMax** : le pas vaut 0.026 N·m sur J1-J2, 0.014 sur J3-J4
et 0.005 sur J5-J7. Il n'y a pas de flux d'état autonome : chaque moteur répond à **chaque
commande** (`send_position`, en MIT) ou à chaque `refresh_all()`. La fréquence de lecture est
donc celle de la boucle de commande (100 Hz ici). Moteurs **non armés**, le couple lu vaut ~0.

**Commander lentement le poignet.** Il n'y a pas d'API de vitesse. On utilise
`send_position(8 positions)` en MIT (PD avec kp/kd de la config), appelé en boucle avec une
consigne qui avance petit à petit. `smooth_move(pos, hz, duration)` interpole aussi, mais il
bloque. Le driver limite la vitesse commandée (`joint_velocity_limits`, 6.3 rad/s sur le
poignet) et coupe tout saut de plus de 1.5 rad (arrêt verrouillé jusqu'à `stop()` puis
`start()`). `Robot` fait tourner un thread qui suit la cible à la vitesse demandée : 3°/s pour
le riz, c'est trivial.

**Pièges relevés dans le code :**
- `start()` joue une trajectoire de départ et `stop()` une trajectoire d'arrêt, **pince
  comprise**, puis désarme (le bras tombe). Avec une bouteille en main, c'est dangereux.
  `OpenArmBackend` neutralise les deux via les hooks `_on_start`/`_on_stop` : armer = tenir la
  pose actuelle, sans aucun mouvement.
- `openarm-can-cli monitor` **arme puis désarme** les moteurs, et il suppose que tous sont des
  DM4310 : ses couples sont faux pour J1-J4 (facteurs ×5.4 et ×2.8).
- La commande MIT laisse une **erreur statique** due à la gravité (environ 0.09 rad sur J2 avec
  kp=70). On ne peut donc pas attendre « position mesurée = cible ».
- Le PPA publie bien des paquets **arm64** (Ubuntu 24.04, v1.4.0) : la VM Parallels peut s'en servir.

## Le couple pour « verser au poids » : ce qu'il faut vérifier sur le vrai robot

Le meilleur candidat est **J2** (DM8009, réducteur 9:1, peu de frottement). Avec 50 g de riz à
~40 cm, on attend ~0.2 N·m, soit environ 8 pas de quantification. J3-J4 sont des 4340 en 40:1
(non QDD) : beaucoup de frottement, donc mauvais candidats.

Ce qui limite vraiment la mesure, c'est le **frottement sec**, plus que le bruit : le couple à
l'arrêt dépend du sens par lequel on arrive à la pose. Le mock le reproduit, et `analyze_torque
--demo` le montre (les courbes vont par paires). D'où le protocole :
1. **Pesée statique** à une pose de référence, toujours atteinte **par le même côté**, avec une
   moyenne sur 1.5 s. Ne pas peser en continu pendant l'inclinaison : le centre de gravité de la
   bouteille bouge et fausse la mesure.
2. Calibration : 5 ou 6 masses connues (0, 25, 50, 100, 150 g), un CSV par masse
   (`log_torque.py --hold --mass-g X`), puis `analyze_torque.py data/weigh_*.csv`. On obtient la
   pente, R², la résolution en grammes et `config/torque_calib.json`.
3. Données gratuites : `log_torque.py --backend sniff` pendant la téléop des coéquipiers.

Les chiffres du mock (environ 30 g de résolution) viennent de paramètres choisis à la main. **Ce
n'est pas un résultat.** La vraie résolution sort de l'étape 2.

## Intégration avec l'équipe

- `pour(robot, ...)` ne fait que changer des cibles sur l'objet `Robot` partagé. Le
  pick & place doit faire pareil (`robot.set_joint_targets`) : voir `orchestrator_example.py`.
- **Point à trancher tôt** : si la policy pick & place tourne dans une dataflow **Dora** (stack
  Enactic) qui ouvre elle-même le driver, il y a deux propriétaires du bus. Deux options :
  appeler la policy distante depuis l'orchestrateur Python (recommandé), ou faire de `pour` un
  nœud Dora.
- Interrompre : lever `stop_event` (ou Ctrl+C). La bouteille est redressée, le bras revient au
  neutre, et la pince n'est jamais touchée. Le vrai arrêt d'urgence reste le bouton physique.

## À régler sur le robot (valeurs par défaut = suppositions)

Dans `PourConfig` : `pour_joint` (J7 par défaut ; J6 est limité à ±45°, trop peu pour verser),
`tilt_sign`, `approach_pose`, `pre_tilt_deg` et `max_tilt_deg`. Les poses de
`orchestrator_example.py` sont aussi à relever. Le plus simple : `log_torque.py --backend sniff`
pendant qu'un coéquipier fait le geste en téléop.
