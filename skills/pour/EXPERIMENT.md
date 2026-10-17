# Protocole expérimental

Deux expériences : (1) peut-on peser les M&M's au couple moteur ? (2) quelle précision
de versement, mesurée à la balance (les chiffres des slides) ?

Matériel : balance de cuisine (0,1 g ou 1 g), M&M's, les 2-3 bouteilles, le grand verre,
le robot armé côté verseur, la caméra du verre calibrée. Tout se lance depuis le Mac :
`./run_on_vm.sh <script> [args]` (résultats rapatriés dans `results/`).

Les commandes qui arment les moteurs sont marquées ⚠. Elles exigent
`--i-understand-motors-will-be-armed` et une personne à l'arrêt d'urgence.

---

## 0. Préparation (une fois, ~20 min, sans moteurs)

1. **Profils des bouteilles** (`containers.yaml`) : peser chaque bouteille vide
   (`empty_mass_g`), mesurer le goulot (`neck_length_m`, `neck_offset_m` depuis la pince),
   noter la contenance réelle.
2. **Caméra du verre** :
   ```bash
   ./run_on_vm.sh glass_level.py --calibrate      # zone : fond du verre -> niveau ~300 g ; touche b = verre VIDE ; s
   ```
   La zone exclut le goulot au maximum. Caméra et éclairage **fixes** ensuite (scotch).
3. **Calibration hauteur → grammes** (le verre n'est pas forcément cylindrique) :
   ```bash
   ./run_on_vm.sh glass_level.py --set-empty      # verre vide en place
   # verser à la main 30 g pesés, puis :
   ./run_on_vm.sh glass_level.py --add-point 30
   # +30 g -> --add-point 60, puis 90, 120, 180, 240, 300
   ```
   Contrôle : la courbe (`config/glass_grams_calib.json`) doit être croissante. Refaire un
   point au hasard. L'écart doit rester sous 5 g.
4. **Relever les poses** pendant une téléop, sans risque :
   `./run_on_vm.sh log_torque.py --backend sniff --duration 0 --label poses`
   → angle de J7 bouteille verticale, sens de basculement (`tilt_sign`), `approach_pose`.

---

## 1. Test couple : peser au couple (~25 min)

**Question** : la différence de couple entre bouteille vide et pleine se voit-elle, et avec
quelle résolution en grammes ?

**Protocole** : masse ajoutée dans la bouteille **0 / 30 / 60 / 90 / 120 g** (pesée à la
balance). Pour chaque palier :
1. bouteille dans la pince, bras à la **pose de pesée** (bouteille verticale, toujours la même) ;
2. arriver à la pose **toujours par le même côté** : petit aller-retour de J2 (et J4) vers le
   bas puis retour. `log_torque.py --hold` le fait si on ajoute `--approach-side` ;
3. enregistrer 5 s à l'arrêt ;
4. répéter 3 fois le palier (on retire et on remet la bouteille) pour voir la répétabilité.

```bash
for g in 0 30 60 90 120; do for k in 1 2 3; do
  ./run_on_vm.sh log_torque.py --backend openarm --hold --approach-side \
     --i-understand-motors-will-be-armed --mass-g $g --duration 5 --out data/weigh_${g}g_$k.csv   # ⚠
done; done
./run_on_vm.sh analyze_torque.py data/weigh_*.csv --joint J2
```

**Ce qu'on mesure** : la **différence** Δτ = τ(m) − τ(bouteille vide), pas le couple brut
(le bras pèse ~6 N·m sur J2). `analyze_torque.py` donne la pente (mN·m/g), R², la résolution
en grammes, et écrit `config/torque_calib.json` (que `pour` utilise ensuite).

**Contrôle du frottement (pour les slides)** : refaire 0 g et 120 g en arrivant
**alternativement par les deux côtés** et comparer l'écart à celui des répétitions. La démo
mock (`analyze_torque.py --demo-random-side`) montre l'effet attendu.

**Critère** : résolution < 10 g → le couple sert de 2e capteur (estimation `poured_g_torque`,
détection d'écoulement, mode sans caméra). Sinon, on le présente honnêtement comme limite
(quantification 0,026 N·m sur J2 ≈ 7 g de M&M's à 40 cm).

Ordre de grandeur attendu : 0,9 g × 9,81 × 0,40 m ≈ 3,5 mN·m par M&M's, soit ~0,4 N·m
pour 120 g.

---

## 2. Évaluation finale (~1 h 30 de robot)

### 2a. 10 versements par cible : 30, 60, 90 g et « vider »

```bash
./run_on_vm.sh eval_pours.py run --backend openarm --i-understand-motors-will-be-armed \
   --container red --targets 30 60 90 all --n 10        # ⚠
```
Pour chaque essai :
- **tarer** la balance avec le verre avant le versement (le script fait une pause) ;
- bouteille en main, verticale au-dessus du verre (Entrée) ;
- le robot verse ; on saisit le **poids ajouté lu sur la balance** (et, pour « vider », ce
  qui reste dans la bouteille) ;
- le script demande de remplir la bouteille / vider le verre quand il le faut.

**Métriques** (tableau imprimé + `plots/eval_errors.png`) :
- erreur moyenne (biais) et erreur absolue moyenne, en grammes ;
- taux de succès : |réel − cible| ≤ 10 g ; « vider » : ≤ 10 g restant dans la bouteille ;
- erreur du capteur (estimé − balance), durée moyenne.

**Réglage du biais** après les 10 premiers essais : biais < 0 (on s'arrête trop tôt) →
baisser `PourConfig.latency_s` ; biais > 0 → l'augmenter. Le dire dans les slides :
un seul paramètre ajusté, sur les données d'évaluation de la 1re série.

### 2b. Trois cocktails complets à deux couleurs ou plus

```bash
./run_on_vm.sh eval_pours.py cocktails --backend openarm --i-understand-motors-will-be-armed \
   --names mojito lagon_bleu sunset        # ⚠
```
Même pesée à la balance après chaque couleur. Succès du cocktail = toutes les couleurs à
±10 g. Le contrôle de couleur de la couche (vision) doit valider chaque bouteille.

### Récupérer les résultats

```bash
./run_on_vm.sh eval_pours.py report data/eval_*.csv data/cocktails_*.csv
open results/plots/eval_errors.png
```

---

## Fiche de suivi (à remplir pendant les essais)

| essai | bouteille | cible | balance (g) | estimé vision (g) | estimé couple (g) | angle départ (°) | remarque |
|---|---|---|---|---|---|---|---|
| 1 | rouge | 30 | | | | | |

À noter dans les slides : nombre d'essais, conditions (bouteille, remplissage au départ),
tout essai exclu et pourquoi.
