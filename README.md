# Nettoyage de dates hétérogènes (`date_cleaner`)

Convertit une colonne de dates **« sales »** — des dates écrites dans des
formats incohérents, mélangés, parfois entourés de texte parasite — en une
colonne `datetime` propre et exploitable.

C'est une tâche très courante en science des données : les dates issues de
saisies manuelles, d'exports de systèmes différents ou de fichiers fusionnés
arrivent rarement dans un format unique. Avant toute analyse temporelle, il
faut les normaliser sans perdre les lignes valides ni inventer de fausses dates.

## Exemple (extrait du jeu de données réel)

| Entrée                          | Sortie       |
|---------------------------------|--------------|
| `2022/11/27`                    | `2022-11-27` |
| `random_text 2007-12-9`         | `2007-12-09` |
| `25th October 1998`             | `1998-10-25` |
| `2004..10..24`                  | `2004-10-24` |
| `2018-07-22T12:45:00 TEXT`      | `2018-07-22` |
| `Date:2023-01-01`               | `2023-01-01` |
| `13-Aug-2023 random`            | `2023-08-13` |
| `2013/12/08Z ???`               | `2013-12-08` |
| `logged:2020-2-23`              | `2020-02-23` |
| `unknown` / `yesterday`         | *(NaT)*      |
| `Feb 30 2020` (date impossible) | *(NaT)*      |

Sur le vrai jeu de données fourni (`dirty_dates_master2_level.csv`, **362 lignes**),
le parseur reconnaît **351 dates (97,0 %)**. Les 11 valeurs restantes sont
exactement celles qui *doivent* rester `NaT` : 3 valeurs manquantes et 8 valeurs
réellement non datables (`unknown`, `yesterday`, dates calendairement impossibles
comme `Feb 30 2020` ou `31/02/2018`).

Autrement dit : **100 % des dates réellement valides sont reconnues, et aucune
fausse date n'est inventée** — un parseur qui « réparerait » `Feb 30` en une vraie
date serait dangereux.

## Modalités gérées

Le jeu de données réel mélange une grande variété de formats et de bruit ; le
parseur les couvre tous :

| Catégorie                | Exemples                                            |
|--------------------------|-----------------------------------------------------|
| Formats numériques       | `2022/11/27`, `21-7-13`, `2004..10..24`, `1997.7.20`|
| Année sur 2 ou 4 chiffres| `21-7-13` → 2013 ; `2005/12/4` (année en tête)      |
| Mois en lettres          | `25th October 1998`, `13-Aug-2023`, `January 22 2017`|
| Suffixes ordinaux        | `25th`, `28th`, `3rd of March`                      |
| Étiquettes / préfixes    | `Date:`, `logged:`, `created on`, `approx`, `update[…]`|
| Mots parasites           | `random`, `random_text`, `TEXT`, `extra words`, `error`, `### … ###`|
| Composante horaire       | `T12:45:00`, ` 00:00:00`                            |
| Fuseaux horaires         | suffixe `Z`, décalage `+02:00`                      |
| Ponctuation parasite     | `???`, espaces multiples, tabulations               |
| Vrais invalides          | `unknown`, `yesterday`, `9999-99-99`, `Feb 30 2020` |

## Approche

Le coeur de l'idée est de **ne pas chercher à tout résoudre d'un coup** avec une
regex unique et fragile. On procède par **passes successives** :

1. On tente un parsing générique sur tout ce qui reste à traiter.
2. On isole **uniquement** les valeurs qui ont échoué.
3. On applique un nettoyage ciblé (regex) à ces échecs pour les rapprocher d'un
   format reconnaissable (suppression des suffixes `1st`/`2nd`, mois abrégés
   développés, mots parasites retirés, séparateurs homogénéisés…).
4. On recommence sur les échecs nettoyés.

On s'arrête quand il ne reste que des valeurs réellement invalides ou
manquantes. Chaque date reconnue est rangée à sa place dans un conteneur de
résultats **aligné sur l'index d'entrée**, donc une ligne en entrée correspond
toujours à une ligne en sortie.

Le parsing se fait **valeur par valeur** : une colonne sale mélange des formats
d'une ligne à l'autre, et chaque valeur peut donc suivre son propre format sans
bloquer les autres.

## Utilisation

```python
import pandas as pd
from date_cleaner import clean_dates

s = pd.Series(["2023-10-22", "March 12 2003", "not a date"])
dates = clean_dates(s)           # -> Series datetime64[ns], NaT pour l'invalide
```

Pour les formats ambigus (`03/04/2020` : 3 avril ou 4 mars ?), le paramètre
`dayfirst` fixe la convention. Par défaut `dayfirst=True` (jour en premier,
convention européenne) ; passez `dayfirst=False` pour la convention américaine.

## Lancer la démonstration et les tests

```bash
pip install -r requirements.txt

python date_cleaner.py          # démonstration sur le jeu RÉEL fourni + rapport chiffré
python test_date_cleaner.py     # suite de tests (ou simplement : pytest)
```

## Contenu du dépôt

| Fichier                            | Rôle                                                  |
|------------------------------------|-------------------------------------------------------|
| `date_cleaner.py`                  | Le parseur (fonction `clean_dates`) et un rapport chiffré |
| `sample_data.py`                   | Échantillon synthétique (une modalité de chaque) + chargeur du CSV |
| `dirty_dates_master2_level.csv`    | Jeu de données réel de 362 dates sales                |
| `test_date_cleaner.py`             | Tests couvrant chaque modalité, les cas limites et le CSV réel |
| `requirements.txt`                 | Dépendances                                           |

## Limites connues

- Pour les dates **entièrement ambiguës** (jour et mois tous deux ≤ 12), la
  convention `dayfirst` tranche arbitrairement : sans information sur la source
  des données, c'est inévitable. Le choix est explicite et documenté plutôt que
  caché.
- Les mois sont reconnus en **anglais** (format des données traitées). Étendre à
  d'autres langues demanderait d'enrichir le dictionnaire de correspondance.
- L'objectif est la **robustesse sur des volumes modérés**, pas la performance
  sur des millions de lignes ; le parsing valeur par valeur privilégie la
  fiabilité face aux formats mélangés.
