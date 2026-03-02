# 🚚 DeliverPro — Backend Django + PostgreSQL

## 📋 Prérequis

- Python 3.11+
- PostgreSQL 14+
- pip

---

## ⚡ Installation en 5 étapes

### 1️⃣ Cloner et configurer l'environnement

```bash
cd deliverpro_backend
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt
```

### 2️⃣ Configurer PostgreSQL

```sql
-- Se connecter à PostgreSQL
sudo -u postgres psql

-- Créer la base et l'utilisateur
CREATE DATABASE deliverpro;
CREATE USER deliverpro_user WITH PASSWORD 'VotreMotDePasse123!';
GRANT ALL PRIVILEGES ON DATABASE deliverpro TO deliverpro_user;
\q
```

### 3️⃣ Configurer les variables d'environnement

```bash
cp .env.example .env
# Éditer .env avec vos vraies valeurs
```

Contenu du `.env` :
```env
DEBUG=True
SECRET_KEY=ma-cle-secrete-tres-longue-et-aleatoire
ALLOWED_HOSTS=localhost,127.0.0.1

# Option 1 (recommande pour Neon)
DATABASE_URL=postgresql://neondb_owner:password@ep-xxxx-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require

# Option 2 (fallback local si DATABASE_URL est vide)
DB_NAME=deliverpro
DB_USER=deliverpro_user
DB_PASSWORD=VotreMotDePasse123!
DB_HOST=localhost
DB_PORT=5432
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:5500
```

### 4️⃣ Migrations et données de démo

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py seed_data
```

### 5️⃣ Lancer le serveur

```bash
python manage.py runserver
```

L'API est disponible sur **http://localhost:8000**

---

## 🔗 Endpoints API

### 🔐 Authentification

| Méthode | URL | Description |
|---------|-----|-------------|
| POST | `/api/auth/login/` | Connexion → retourne JWT |
| POST | `/api/auth/logout/` | Déconnexion (blacklist token) |
| GET | `/api/auth/me/` | Profil utilisateur connecté |
| PATCH | `/api/auth/me/` | Modifier son profil |
| POST | `/api/auth/change-password/` | Changer mot de passe |
| POST | `/api/auth/refresh/` | Rafraîchir le token JWT |

**Exemple de connexion :**
```json
POST /api/auth/login/
{
  "email": "admin@deliverpro.com",
  "password": "Admin123!"
}
```
**Réponse :**
```json
{
  "access": "eyJ...",
  "refresh": "eyJ...",
  "user": { "id": 1, "nom": "Admin Principal", "role": "admin" }
}
```

### 📊 Dashboard

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/dashboard/?periode=mois` | Dashboard admin (jour/semaine/mois/annee) |
| GET | `/api/dashboard/livreur/` | Dashboard livreur |

### 🏢 Entreprises (Admin)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/entreprises/` | Liste entreprises |
| POST | `/api/entreprises/` | Créer entreprise |
| GET | `/api/entreprises/{id}/` | Détail entreprise |
| PUT/PATCH | `/api/entreprises/{id}/` | Modifier |
| DELETE | `/api/entreprises/{id}/` | Supprimer |
| GET | `/api/entreprises/{id}/dashboard/` | Dashboard entreprise |

### 📦 Commandes

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/commandes/` | Liste (filtrée selon le rôle) |
| POST | `/api/commandes/` | Créer (Admin) |
| GET | `/api/commandes/{id}/` | Détail |
| PATCH | `/api/commandes/{id}/` | Modifier |
| DELETE | `/api/commandes/{id}/` | Supprimer (Admin) |
| POST | `/api/commandes/{id}/demarrer/` | Livreur démarre |
| POST | `/api/commandes/{id}/livrer/` | Livreur livre |
| POST | `/api/commandes/{id}/payer/` | Livreur encaisse |

**Filtres disponibles :**
```
GET /api/commandes/?statut=en+attente
GET /api/commandes/?entreprise=1&date_debut=2025-01-01&date_fin=2025-01-31
GET /api/commandes/?livreur=2
```

### 💰 Transactions (Admin)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/transactions/` | Journal complet |
| POST | `/api/transactions/` | Ajouter dépense manuelle |
| GET | `/api/transactions/?type=revenu` | Filtrer par type |

### 👥 Utilisateurs/Livreurs (Admin)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/users/` | Liste utilisateurs |
| POST | `/api/users/` | Créer livreur/admin |
| PATCH | `/api/users/{id}/` | Modifier |
| POST | `/api/users/{id}/toggle_actif/` | Activer/désactiver |
| GET | `/api/users/{id}/stats/` | Stats livreur |

### 🎯 Objectifs (Admin)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/objectifs/` | Liste objectifs |
| POST | `/api/objectifs/` | Créer objectif |
| PATCH | `/api/objectifs/{id}/` | Modifier |

### 📄 Export PDF (Admin)

```json
POST /api/export/pdf/
{
  "date_debut": "2025-01-01",
  "date_fin": "2025-01-31",
  "entreprise_id": 1,
  "livreur_id": null,
  "type": "complet"
}
```
Retourne un fichier PDF binaire.

---

## 🔐 Authentification JWT

Ajouter le header sur toutes les requêtes :
```
Authorization: Bearer <access_token>
```

---

## 📖 Documentation Swagger

Accessible à : **http://localhost:8000/api/docs/**

---

## 🗂️ Structure du projet

```
deliverpro_backend/
├── manage.py
├── requirements.txt
├── .env.example
├── deliverpro/
│   ├── settings.py       ← Configuration Django
│   ├── urls.py           ← Routes principales
│   └── wsgi.py
└── api/
    ├── models.py         ← User, Entreprise, Commande, Transaction, Objectif, AuditLog
    ├── serializers.py    ← Sérialisation DRF
    ├── views.py          ← Vues et logique métier
    ├── urls.py           ← Routes API
    ├── permissions.py    ← IsAdmin, IsLivreur, IsOwnerOrAdmin
    ├── filters.py        ← Filtres django-filter
    ├── utils.py          ← Audit log + génération PDF
    ├── admin.py          ← Interface admin Django
    └── management/
        └── commands/
            └── seed_data.py  ← Données de démo
```

---

## 🚀 Déploiement Production

```bash
# Variables d'environnement
DEBUG=False
SECRET_KEY=cle-aleatoire-longue-64-chars

# Collecte des fichiers statiques
python manage.py collectstatic

# Gunicorn
pip install gunicorn
gunicorn deliverpro.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

---

## 🔑 Comptes de démo (après seed_data)

| Rôle | Email | Mot de passe |
|------|-------|--------------|
| Admin | admin@deliverpro.com | Admin123! |
| Livreur 1 | jean@deliverpro.com | Livr123! |
| Livreur 2 | marie@deliverpro.com | Livr123! |
---

## Nouvelles fonctionnalites API ajoutees

- POST `/api/transactions/ajouter-revenu/` (Admin)
- POST `/api/transactions/ajouter-depense/` (Admin)
- GET `/api/transactions/my-history/` (Livreur)
- GET `/api/budget/alerts/?seuil=80` (Admin)
- POST `/api/users/update_location/` (Livreur)
- GET `/api/users/livreurs_positions/` (Admin)
- Dashboard et dashboard entreprise avec cache, alertes et graphiques
- Export PDF avec signature automatique (nom signataire) + filtre livreur sur transactions
- Temps reel WebSocket: `ws://<host>/ws/updates/?token=<JWT_ACCESS_TOKEN>`

---

## Deploiement sur Render (Blueprint)

Le repo contient un fichier [render.yaml](./render.yaml).

1. Push le projet sur GitHub.
2. Dans Render: `New +` -> `Blueprint` -> selectionne le repo.
3. Remplace ces variables avant le premier deploy:
   - `DATABASE_URL` = URL Neon
   - `CORS_ALLOWED_ORIGINS` = URL de ton frontend
   - `CSRF_TRUSTED_ORIGINS` = URL Render de l'API + URL frontend
4. Lance le deploy.

Commande de demarrage configuree:

```bash
python manage.py migrate --noinput && gunicorn deliverpro.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 120
```
