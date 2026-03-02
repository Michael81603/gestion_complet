-- ============================================================
-- DeliverPro — Schéma PostgreSQL Complet
-- Exécuter dans l'ordre après avoir créé la base de données
-- ============================================================

-- Connexion:
-- psql -U deliverpro_user -d deliverpro -f database_schema.sql

-- ─────────────────────────────────────────────────────────────
-- EXTENSIONS
-- ─────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─────────────────────────────────────────────────────────────
-- TABLE: api_user
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_user (
    id          BIGSERIAL PRIMARY KEY,
    nom         VARCHAR(150) NOT NULL,
    email       VARCHAR(150) UNIQUE NOT NULL,
    password    VARCHAR(255) NOT NULL,
    role        VARCHAR(20)  NOT NULL DEFAULT 'livreur'
                CHECK (role IN ('admin', 'livreur')),
    telephone   VARCHAR(20),
    actif       BOOLEAN DEFAULT TRUE,
    is_staff    BOOLEAN DEFAULT FALSE,
    is_active   BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    last_login  TIMESTAMP WITH TIME ZONE,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- TABLE: api_entreprise
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_entreprise (
    id              BIGSERIAL PRIMARY KEY,
    nom             VARCHAR(200) NOT NULL,
    adresse         TEXT,
    telephone       VARCHAR(20),
    date_creation   DATE DEFAULT CURRENT_DATE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- TABLE: api_commande
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_commande (
    id              BIGSERIAL PRIMARY KEY,
    entreprise_id   BIGINT NOT NULL REFERENCES api_entreprise(id) ON DELETE RESTRICT,
    livreur_id      BIGINT REFERENCES api_user(id) ON DELETE SET NULL,
    client_nom      VARCHAR(200) NOT NULL,
    adresse         TEXT NOT NULL,
    telephone       VARCHAR(20),
    prix            DECIMAL(10, 2) NOT NULL DEFAULT 0,
    cout_livraison  DECIMAL(10, 2) NOT NULL DEFAULT 0,
    depense         DECIMAL(10, 2) DEFAULT 0,
    statut          VARCHAR(20) NOT NULL DEFAULT 'en attente'
                    CHECK (statut IN ('en attente', 'en cours', 'livrée', 'payée')),
    date            DATE NOT NULL DEFAULT CURRENT_DATE,
    date_livraison  TIMESTAMP WITH TIME ZONE,
    date_paiement   TIMESTAMP WITH TIME ZONE,
    notes           TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- TABLE: api_transaction
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_transaction (
    id              BIGSERIAL PRIMARY KEY,
    type            VARCHAR(10) NOT NULL CHECK (type IN ('revenu', 'depense')),
    montant         DECIMAL(10, 2) NOT NULL,
    label           VARCHAR(300) NOT NULL,
    commande_id     BIGINT REFERENCES api_commande(id) ON DELETE SET NULL,
    entreprise_id   BIGINT REFERENCES api_entreprise(id) ON DELETE SET NULL,
    user_id         BIGINT REFERENCES api_user(id) ON DELETE SET NULL,
    date            DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- TABLE: api_objectif
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_objectif (
    id          BIGSERIAL PRIMARY KEY,
    type        VARCHAR(20) NOT NULL CHECK (type IN ('revenu', 'depense')),
    montant     DECIMAL(10, 2) NOT NULL,
    periode     VARCHAR(20) DEFAULT 'mensuel'
                CHECK (periode IN ('hebdomadaire', 'mensuel', 'annuel')),
    label       VARCHAR(200),
    mois        INTEGER CHECK (mois BETWEEN 1 AND 12),
    annee       INTEGER,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- TABLE: api_auditlog
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_auditlog (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT REFERENCES api_user(id) ON DELETE SET NULL,
    action      VARCHAR(100) NOT NULL,
    table_name  VARCHAR(50) DEFAULT '',
    record_id   BIGINT,
    details     JSONB,
    ip_address  INET,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- INDEX DE PERFORMANCE
-- ─────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_commande_livreur     ON api_commande(livreur_id);
CREATE INDEX IF NOT EXISTS idx_commande_entreprise  ON api_commande(entreprise_id);
CREATE INDEX IF NOT EXISTS idx_commande_statut      ON api_commande(statut);
CREATE INDEX IF NOT EXISTS idx_commande_date        ON api_commande(date);
CREATE INDEX IF NOT EXISTS idx_transaction_type     ON api_transaction(type);
CREATE INDEX IF NOT EXISTS idx_transaction_date     ON api_transaction(date);
CREATE INDEX IF NOT EXISTS idx_transaction_entreprise ON api_transaction(entreprise_id);
CREATE INDEX IF NOT EXISTS idx_user_email           ON api_user(email);
CREATE INDEX IF NOT EXISTS idx_user_role            ON api_user(role);
CREATE INDEX IF NOT EXISTS idx_auditlog_action      ON api_auditlog(action);
CREATE INDEX IF NOT EXISTS idx_auditlog_created     ON api_auditlog(created_at);

-- ─────────────────────────────────────────────────────────────
-- TRIGGER: Auto updated_at
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_commande_updated_at
BEFORE UPDATE ON api_commande
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_user_updated_at
BEFORE UPDATE ON api_user
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────────────────────────
-- TRIGGER: Auto-créer transactions quand statut = 'payée'
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION auto_transaction_paiement()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.statut = 'payée' AND OLD.statut <> 'payée' THEN
        -- Revenu
        INSERT INTO api_transaction (type, montant, label, commande_id, entreprise_id, user_id, date)
        VALUES (
            'revenu',
            NEW.prix,
            'Paiement commande #' || NEW.id || ' — ' || NEW.client_nom,
            NEW.id,
            NEW.entreprise_id,
            NEW.livreur_id,
            CURRENT_DATE
        )
        ON CONFLICT DO NOTHING;

        -- Dépense livraison
        IF (NEW.cout_livraison + COALESCE(NEW.depense, 0)) > 0 THEN
            INSERT INTO api_transaction (type, montant, label, commande_id, entreprise_id, user_id, date)
            VALUES (
                'depense',
                NEW.cout_livraison + COALESCE(NEW.depense, 0),
                'Coût livraison + dépenses commande #' || NEW.id,
                NEW.id,
                NEW.entreprise_id,
                NEW.livreur_id,
                CURRENT_DATE
            );
        END IF;

        NEW.date_paiement = NOW();
    END IF;

    IF NEW.statut IN ('livrée', 'payée') AND OLD.statut NOT IN ('livrée', 'payée') THEN
        NEW.date_livraison = NOW();
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_auto_transaction
BEFORE UPDATE ON api_commande
FOR EACH ROW EXECUTE FUNCTION auto_transaction_paiement();

-- ─────────────────────────────────────────────────────────────
-- VUES UTILES
-- ─────────────────────────────────────────────────────────────

-- Résumé financier global
CREATE OR REPLACE VIEW vue_resume_financier AS
SELECT
    COALESCE(SUM(CASE WHEN type = 'revenu'  THEN montant ELSE 0 END), 0) AS revenus_total,
    COALESCE(SUM(CASE WHEN type = 'depense' THEN montant ELSE 0 END), 0) AS depenses_total,
    COALESCE(SUM(CASE WHEN type = 'revenu'  THEN montant ELSE 0 END), 0) -
    COALESCE(SUM(CASE WHEN type = 'depense' THEN montant ELSE 0 END), 0) AS benefice_net
FROM api_transaction;

-- Stats par entreprise
CREATE OR REPLACE VIEW vue_entreprises_stats AS
SELECT
    e.id,
    e.nom,
    COUNT(DISTINCT c.id) AS nb_commandes,
    COALESCE(SUM(CASE WHEN t.type='revenu'  THEN t.montant END), 0) AS revenus,
    COALESCE(SUM(CASE WHEN t.type='depense' THEN t.montant END), 0) AS depenses,
    COALESCE(SUM(CASE WHEN t.type='revenu'  THEN t.montant END), 0) -
    COALESCE(SUM(CASE WHEN t.type='depense' THEN t.montant END), 0) AS benefice
FROM api_entreprise e
LEFT JOIN api_commande    c ON c.entreprise_id = e.id
LEFT JOIN api_transaction t ON t.entreprise_id = e.id
GROUP BY e.id, e.nom;

-- Stats par livreur
CREATE OR REPLACE VIEW vue_livreurs_stats AS
SELECT
    u.id,
    u.nom,
    u.email,
    COUNT(c.id) AS total_commandes,
    COUNT(CASE WHEN c.statut IN ('livrée','payée') THEN 1 END) AS livrees,
    COUNT(CASE WHEN c.statut = 'payée'             THEN 1 END) AS payees,
    COALESCE(SUM(CASE WHEN c.statut='payée' THEN c.prix END), 0) AS montant_encaisse
FROM api_user u
LEFT JOIN api_commande c ON c.livreur_id = u.id
WHERE u.role = 'livreur'
GROUP BY u.id, u.nom, u.email;

-- ─────────────────────────────────────────────────────────────
-- FIN DU SCHÉMA
-- ─────────────────────────────────────────────────────────────
