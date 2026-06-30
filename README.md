# DeskSwap

Gestionnaire de fichiers web léger, auto-hébergé, conçu pour transférer des fichiers entre une machine virtuelle et une machine hôte sur le même réseau local.

Interface moderne avec thème sombre, accessible depuis n'importe quel navigateur sur le LAN — aucune installation côté client requise.

![Python](https://img.shields.io/badge/Python-3.11-blue) ![Flask](https://img.shields.io/badge/Flask-3.1-green) ![Docker](https://img.shields.io/badge/Docker-ready-2496ED)

---

## Fonctionnalités

- **Navigation** — explorateur de fichiers avec fil d'Ariane, tri par nom/taille/date, fichiers cachés optionnels
- **Téléchargement** — fichiers individuels ou sélection multiple en ZIP, avec limite configurable
- **Upload** — glisser-déposer ou sélection, barre de progression en temps réel, jusqu'à 10 Go par défaut
- **Suppression** — fichiers et dossiers avec confirmation modale
- **Prévisualisation** — images, PDF et fichiers texte/code directement dans le navigateur
- **Recherche** — recherche récursive dans l'arborescence avec limite de profondeur
- **Métriques** — utilisation disque, RAM et CPU en temps réel

---

## Déploiement

### Prérequis

- Docker et Docker Compose installés sur la machine hôte (VM)

### Lancement rapide

```bash
git clone https://github.com/your-username/deskswap.git
cd deskswap
docker compose up --build -d
```

L'interface est accessible sur `http://<IP-de-la-VM>:8080`.

### Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `CONTAINER_PORT` | `8080` | Port exposé sur l'hôte |
| `HOST_PATH` | `/home/user` | Dossier racine monté dans le conteneur |
| `MAX_UPLOAD_SIZE` | `10737418240` (10 Go) | Taille maximale d'un upload en octets |
| `MAX_ZIP_SIZE` | `4294967296` (4 Go) | Taille maximale d'un téléchargement ZIP en octets |
| `MAX_SEARCH_DEPTH` | `10` | Profondeur maximale de la recherche récursive |

Exemple avec un dossier et un port personnalisés :

```bash
CONTAINER_PORT=9090 HOST_PATH=/mnt/data docker compose up -d
```

---

## Stack technique

- **Backend** : Python 3.11 / Flask 3.1
- **Frontend** : HTML + CSS + JavaScript vanilla (aucune dépendance externe)
- **Conteneurisation** : Docker (Alpine Linux, utilisateur non-root)

---

<div align="center">

Fait avec soin par **Liam** - License MIT — voir [LICENSE](LICENSE)

</div>
