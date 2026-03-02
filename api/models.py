"""
DeliverPro — Modèles de base de données
"""
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


# ─────────────────────────────────────────────────────────────────────────────
# USER MODEL
# ─────────────────────────────────────────────────────────────────────────────

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("L'email est requis")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('admin', 'Administrateur'),
        ('livreur', 'Livreur'),
    ]

    nom        = models.CharField(max_length=150, verbose_name="Nom complet")
    email      = models.EmailField(unique=True, verbose_name="Email")
    role       = models.CharField(max_length=20, choices=ROLE_CHOICES, default='livreur')
    telephone  = models.CharField(max_length=20, blank=True, null=True)
    actif      = models.BooleanField(default=True)
    last_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_location_at = models.DateTimeField(null=True, blank=True)
    is_staff   = models.BooleanField(default=False)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nom']

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.nom} ({self.role})"

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_livreur(self):
        return self.role == 'livreur'


# ─────────────────────────────────────────────────────────────────────────────
# ENTREPRISE MODEL
# ─────────────────────────────────────────────────────────────────────────────

class Entreprise(models.Model):
    nom            = models.CharField(max_length=200, verbose_name="Nom")
    adresse        = models.TextField(blank=True, null=True, verbose_name="Adresse")
    telephone      = models.CharField(max_length=20, blank=True, null=True)
    date_creation  = models.DateField(default=timezone.now)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Entreprise"
        verbose_name_plural = "Entreprises"
        ordering = ['nom']

    def __str__(self):
        return self.nom

    def get_stats(self):
        from django.db.models import Sum, Count
        from decimal import Decimal
        txns = self.transactions.all()
        revenus  = txns.filter(type='revenu').aggregate(t=Sum('montant'))['t'] or Decimal('0')
        depenses = txns.filter(type='depense').aggregate(t=Sum('montant'))['t'] or Decimal('0')
        return {
            'revenus':   revenus,
            'depenses':  depenses,
            'benefice':  revenus - depenses,
            'nb_commandes': self.commandes.count(),
        }


class EntrepriseAccess(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='entreprise_accesses')
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='user_accesses')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Accès entreprise"
        verbose_name_plural = "Accès entreprises"
        constraints = [
            models.UniqueConstraint(fields=['user', 'entreprise'], name='uniq_user_entreprise_access'),
        ]
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['entreprise']),
        ]

    def __str__(self):
        return f"{self.user.nom} -> {self.entreprise.nom}"


# ─────────────────────────────────────────────────────────────────────────────
# COMMANDE MODEL
# ─────────────────────────────────────────────────────────────────────────────

class Commande(models.Model):
    STATUT_CHOICES = [
        ('en attente', 'En attente'),
        ('en cours',   'En cours'),
        ('livrée',     'Livrée'),
        ('payée',      'Payée'),
    ]

    entreprise      = models.ForeignKey(Entreprise, on_delete=models.PROTECT, related_name='commandes')
    livreur         = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='commandes', limit_choices_to={'role': 'livreur'})
    client_nom      = models.CharField(max_length=200, verbose_name="Nom client")
    adresse         = models.TextField(verbose_name="Adresse de livraison")
    latitude        = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude       = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    telephone       = models.CharField(max_length=20, blank=True, null=True)
    prix            = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cout_livraison  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    depense         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    statut          = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en attente')
    date            = models.DateField(default=timezone.now)
    date_livraison  = models.DateTimeField(null=True, blank=True)
    date_paiement   = models.DateTimeField(null=True, blank=True)
    date_demarrage  = models.DateTimeField(null=True, blank=True)
    notes           = models.TextField(blank=True, null=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Commande"
        verbose_name_plural = "Commandes"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['statut']),
            models.Index(fields=['date']),
            models.Index(fields=['livreur']),
            models.Index(fields=['entreprise']),
        ]

    def __str__(self):
        return f"Commande #{self.id} — {self.client_nom}"

    def save(self, *args, **kwargs):
        # Auto-set date_demarrage
        if self.statut == 'en cours' and not self.date_demarrage:
            self.date_demarrage = timezone.now()
        # Auto-set date_livraison
        if self.statut in ('livrée', 'payée') and not self.date_livraison:
            self.date_livraison = timezone.now()
        # Auto-set date_paiement and create transactions
        if self.statut == 'payée' and not self.date_paiement:
            self.date_paiement = timezone.now()
            super().save(*args, **kwargs)
            self._create_transactions()
            return
        super().save(*args, **kwargs)

    def _create_transactions(self):
        """Crée automatiquement les transactions revenu/dépense."""
        today = timezone.now().date()
        # Revenu
        Transaction.objects.get_or_create(
            commande=self,
            type='revenu',
            defaults={
                'montant':      self.prix,
                'label':        f'Paiement commande #{self.id} — {self.client_nom}',
                'entreprise':   self.entreprise,
                'user':         self.livreur,
                'date':         today,
            }
        )
        # Dépense livraison
        total_dep = self.cout_livraison + self.depense
        if total_dep > 0:
            Transaction.objects.get_or_create(
                commande=self,
                type='depense',
                defaults={
                    'montant':    total_dep,
                    'label':      f'Coût livraison + dépense #{self.id}',
                    'entreprise': self.entreprise,
                    'user':       self.livreur,
                    'date':       today,
                }
            )


# ─────────────────────────────────────────────────────────────────────────────
# TRANSACTION MODEL
# ─────────────────────────────────────────────────────────────────────────────

class Transaction(models.Model):
    TYPE_CHOICES = [
        ('revenu',  'Revenu'),
        ('depense', 'Dépense'),
    ]

    type         = models.CharField(max_length=10, choices=TYPE_CHOICES)
    montant      = models.DecimalField(max_digits=10, decimal_places=2)
    label        = models.CharField(max_length=300)
    commande     = models.ForeignKey(Commande, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    entreprise   = models.ForeignKey(Entreprise, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    user         = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    date         = models.DateField(default=timezone.now)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['type']),
            models.Index(fields=['date']),
            models.Index(fields=['entreprise']),
        ]

    def __str__(self):
        return f"{self.type.capitalize()} — {self.montant}€ — {self.date}"


# ─────────────────────────────────────────────────────────────────────────────
# OBJECTIF MODEL
# ─────────────────────────────────────────────────────────────────────────────

class Objectif(models.Model):
    TYPE_CHOICES = [
        ('revenu',  'Objectif Revenu'),
        ('depense', 'Budget Dépenses'),
    ]
    PERIODE_CHOICES = [
        ('hebdomadaire', 'Hebdomadaire'),
        ('mensuel',      'Mensuel'),
        ('annuel',       'Annuel'),
    ]

    type      = models.CharField(max_length=20, choices=TYPE_CHOICES)
    montant   = models.DecimalField(max_digits=10, decimal_places=2)
    periode   = models.CharField(max_length=20, choices=PERIODE_CHOICES, default='mensuel')
    label     = models.CharField(max_length=200, blank=True)
    mois      = models.IntegerField(null=True, blank=True)
    annee     = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Objectif"
        verbose_name_plural = "Objectifs"

    def __str__(self):
        return f"{self.label or self.type} — {self.montant}€"


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT LOG MODEL
# ─────────────────────────────────────────────────────────────────────────────

class AuditLog(models.Model):
    user        = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action      = models.CharField(max_length=100)
    table_name  = models.CharField(max_length=50, blank=True)
    record_id   = models.IntegerField(null=True, blank=True)
    details     = models.JSONField(null=True, blank=True)
    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Journal d'audit"
        verbose_name_plural = "Journal d'audit"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} — {self.action} — {self.created_at}"
