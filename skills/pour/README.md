# skills/pour : skill « barman » pour OpenArm (ERH Physical AI Hackathon, track Daidai)

Importée depuis `Nailec101/pour-skill` avec `git subtree` (historique conservé).
Tous les chemins (`config/`, `data/`, `plots/`, `state/`) sont relatifs à ce dossier,
quel que soit le dossier courant.

Un bras tient le grand verre. L'autre prend une bouteille de M&M's (une couleur = une
« boisson ») et verse en boucle fermée **30, 60 ou 90 g, ou toute la bouteille**. Un cocktail,
c'est plusieurs couleurs versées l'une après l'autre dans le même verre (mojito = 60 g rouge +
90 g jaune). La vision mesure les grammes ajoutés dans le verre. Le couple moteur pèse la
bouteille et détecte le début de l'écoulement.

```
__init__.py             from skills.pour import pour, Robot, BarState (depuis la racine du repo)
containers.yaml         profils des bouteilles (couleur, masse à vide, goulot, vitesses) + cocktails
bar_state.py            état : grammes restants par bouteille, verre, contrôles, résumé pour le LLM
pour_skill.py           pour(robot, target_grams | "all", container, sensor, state)
glass_level.py          "balance optique" : diff cumulatif, calibration hauteur->grammes, couleur
robot_io.py             Robot partagé : backends mock / openarm / sniff (écoute CAN passive)
orchestrator_example.py une connexion, plan LLM -> pick -> pour -> reposer, par couleur
log_torque.py / analyze_torque.py   test couple (Δ vs bouteille vide), figures
eval_pours.py           évaluation pour les slides (10 essais/cible + cocktails, vérité = balance)
EXPERIMENT.md           protocoles
sync_to_vm.sh / run_on_vm.sh   tout piloter depuis le Mac (ssh robotvm)
VM_SETUP.md / setup_robot_vm.sh   VM Ubuntu ARM64 dans Parallels, PPA OpenArm, SocketCAN
```

## Démarrage

Depuis la racine du repo, avec l'environnement uv de l'équipe. Les dépendances de la skill
(`requirements.txt`) sont ajoutées à la volée, sans toucher à `pyproject.toml` ni à `uv.lock` :

```bash
alias pour-py='uv run --with-requirements skills/pour/requirements.txt python'
pour-py skills/pour/pour_skill.py --container red --grams 60        # simulation (mock)
pour-py skills/pour/pour_skill.py --container yellow --grams all
pour-py skills/pour/orchestrator_example.py --prompt "un mojito s'il te plaît"
pour-py skills/pour/orchestrator_example.py --context   # le JSON donné au LLM
pour-py skills/pour/eval_pours.py run --targets 30 60 --n 3   # mini-évaluation simulée
pour-py skills/pour/tests/test_basics.py
```

Depuis l'orchestrateur (racine du repo) :

```python
from skills.pour import BarState, Robot, load_bar_config, pour
```

Les scripts se lancent aussi depuis ce dossier (`cd skills/pour && python pour_skill.py ...`).
Pilotage de la VM robot depuis le Mac (`ssh robotvm`, voir VM_SETUP.md) :

```bash
skills/pour/run_on_vm.sh log_torque.py --backend sniff --duration 20   # écoute passive
```

## Comment `pour` fonctionne

1. **Contrôles avant tout mouvement** (`BarState.check_pour`). Si la quantité demandée dépasse
   ce qui reste dans la bouteille ou la place dans le verre, c'est un `PourRequestError` et rien
   ne bouge. `strict=False` verse ce qui reste. Un cocktail entier est validé d'avance
   (`check_plan`).
2. **Pesée** de la bouteille au couple (J2), en arrivant toujours du même côté.
3. **Photo de référence** du verre dans son état actuel. Seul ce qui s'ajoute par-dessus est
   mesuré.
4. **Pré-inclinaison rapide** jusqu'au dernier angle de départ connu pour cette bouteille, moins
   une marge. **Rampe lente** jusqu'à détecter l'écoulement : le verre prend +3 g, ou le couple
   décroche de sa ligne de base. L'angle de départ dépend du remplissage : il est mesuré à chaque
   fois, puis mémorisé.
5. **Régulation du débit** par l'inclinaison (12 g/s, puis 5 g/s près de la cible). On s'arrête
   à cible − débit × latence, pour compter les M&M's encore en vol. En mode « vider » : on
   incline jusqu'au max, puis on attend 1,5 s de niveau stable, avec un timeout.
6. On redresse, on mesure (+ contrôle de couleur de la nouvelle couche), on repèse, on revient
   au neutre et on met à jour `BarState`.

Sans caméra, la skill verse par impulsions avec une pesée au couple entre chacune. Une
interruption (stop, timeout, capteur perdu, Ctrl+C) redresse toujours la bouteille. La pince
n'est jamais touchée.

### En simulation (mock, ce n'est pas un résultat)
| demande | versé (vérité mock) |
|---|---|
| 30 g / 60 g / 90 g | 26–29 g / 55–58 g / 86 g |
| vider (120 g) | 120 g, bouteille à 0 |
| mojito 60 rouge + 90 jaune | 57,6 + 88,2 g |
| 30 g sans caméra (couple seul) | 27,9 g |

Le biais d'environ −2 g se règle avec `PourConfig.latency_s` après la première série réelle
(EXPERIMENT.md).

## Ce que dit le SDK (lu dans `vendor/`)

- **Noms** : `"right_arm"` est sur `can0`, `"left_arm"` sur `can1`. Chaque bras a 8 moteurs
  (J1–J7 + pince), IDs 0x01–0x08, réponses 0x11–0x18. DM8009 pour J1–J2, DM4340 pour J3–J4,
  DM4310 pour J5–J8.
- **Couple** : `fetch_state()["qtorque"]` est une estimation tirée du courant, codée sur
  12 bits. Le pas vaut 0,026 N·m sur J2, soit environ 7 g de M&M's à 40 cm. Un moteur ne répond
  que quand on lui envoie une commande : on lit donc à la fréquence de la boucle (100 Hz).
  Moteurs non armés, le couple vaut ~0.
- **Poignet lent** : `send_position()` en boucle avec une consigne qui avance pas à pas
  (thread de `Robot`).
- **Pièges** :
  - `start()`/`stop()` jouent des trajectoires qui bougent aussi la pince. `stop()` désarme
    ensuite, et une bouteille en main peut tomber. Le backend les neutralise.
  - `openarm-can-cli monitor` arme puis désarme les moteurs, et ses couples sont faux pour J1–J4.
  - La commande MIT laisse une erreur statique due à la gravité.
  - Le PPA OpenArm publie bien des paquets arm64.

## Intégration avec l'équipe

- Une seule connexion `Robot` et un seul `BarState`, créés par l'orchestrateur et passés aux
  skills. Le contexte pour le LLM vient de `llm_context()` : skills installées, bouteilles,
  verre, cocktails faisables ou non, et pourquoi.
- **À trancher** : si la policy pick & place tourne dans une dataflow Dora qui ouvre elle-même le
  driver, il y a deux propriétaires du bus.
- **À régler sur le robot** : `pour_joint` (J7 ?), `tilt_sign`, l'angle de J7 bouteille verticale,
  les `approach_pose`. Le plus simple est de les relever avec le sniff pendant une téléop.
