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
    ]

    nom        = models.CharField(max_length=150, verbose_name="Nom complet")
    email      = models.EmailField(unique=True, verbose_name="Email")
    role       = models.CharField(max_length=20, choices=ROLE_CHOICES, default='admin')
    telephone  = models.CharField(max_length=20, blank=True, null=True)
    actif      = models.BooleanField(default=True)
    is_staff   = models.BooleanField(default=True)
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
        return f"{self.nom} ({self.email})"

    @property
    def is_admin(self):
        return self.role == 'admin'


# ─────────────────────────────────────────────────────────────────────────────
# ENTREPRISE MODEL
# ─────────────────────────────────────────────────────────────────────────────

class Entreprise(models.Model):
    nom            = models.CharField(max_length=200, verbose_name="Nom")
    adresse        = models.TextField(blank=True, null=True, verbose_name="Adresse")
    telephone      = models.CharField(max_length=20, blank=True, null=True)
    date_creation  = models.DateField(default=timezone.localdate)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Entreprise"
        verbose_name_plural = "Entreprises"
        ordering = ['nom']

    def __str__(self):
        return self.nom

    def get_stats(self):
        from django.db.models import Sum
        from decimal import Decimal
        txns = self.transactions.all()
        revenus  = txns.filter(type='revenu').aggregate(t=Sum('montant'))['t'] or Decimal('0')
        depenses = txns.filter(type='depense').aggregate(t=Sum('montant'))['t'] or Decimal('0')
        return {
            'revenus':   revenus,
            'depenses':  depenses,
            'benefice':  revenus - depenses,
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
# TRANSACTION MODEL
# ─────────────────────────────────────────────────────────────────────────────

class Transaction(models.Model):
    TYPE_CHOICES = [
        ('revenu',  'Revenu'),
        ('depense', 'Dépense'),
    ]
    CATEGORIE_CHOICES = [
        ('vente', 'Vente'),
        ('prestation', 'Prestation'),
        ('salaire', 'Salaire'),
        ('loyer', 'Loyer'),
        ('fournitures', 'Fournitures'),
        ('transport', 'Transport'),
        ('utilitaires', 'Utilitaires'),
        ('maintenance', 'Maintenance'),
        ('marketing', 'Marketing'),
        ('autre', 'Autre'),
    ]

    type         = models.CharField(max_length=10, choices=TYPE_CHOICES)
    categorie    = models.CharField(max_length=20, choices=CATEGORIE_CHOICES, default='autre')
    montant      = models.DecimalField(max_digits=10, decimal_places=2)
    label        = models.CharField(max_length=300)
    entreprise   = models.ForeignKey(Entreprise, on_delete=models.PROTECT, related_name='transactions')
    user         = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    date         = models.DateField(default=timezone.localdate)
    description  = models.TextField(blank=True, null=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['type']),
            models.Index(fields=['date']),
            models.Index(fields=['entreprise']),
            models.Index(fields=['categorie']),
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
        ('personnalise', 'Personnalisé'),
    ]

    type      = models.CharField(max_length=20, choices=TYPE_CHOICES)
    categorie = models.CharField(
        max_length=20,
        choices=Transaction.CATEGORIE_CHOICES,
        blank=True,
        null=True,
        verbose_name="Catégorie de dépense",
    )
    entreprise = models.ForeignKey(
        Entreprise,
        on_delete=models.PROTECT,
        related_name='objectifs',
        blank=True,
        null=True,
        verbose_name="Entreprise ciblée",
    )
    montant   = models.DecimalField(max_digits=10, decimal_places=2)
    periode   = models.CharField(max_length=20, choices=PERIODE_CHOICES, default='mensuel')
    label     = models.CharField(max_length=200, blank=True)
    date_debut = models.DateField(null=True, blank=True)
    date_fin   = models.DateField(null=True, blank=True)
    mois      = models.IntegerField(null=True, blank=True)
    annee     = models.IntegerField(null=True, blank=True)
    seuil_alerte = models.PositiveSmallIntegerField(default=80)
    notification_email = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Objectif"
        verbose_name_plural = "Objectifs"

    def __str__(self):
        return f"{self.label or self.type} — {self.montant}€"


class BudgetNotification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='budget_notifications')
    objectif = models.ForeignKey(Objectif, on_delete=models.CASCADE, related_name='notifications')
    niveau = models.CharField(max_length=30)
    periode_cle = models.CharField(max_length=80)
    email_to = models.EmailField()
    total = models.DecimalField(max_digits=12, decimal_places=2)
    montant_objectif = models.DecimalField(max_digits=12, decimal_places=2)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notification budget"
        verbose_name_plural = "Notifications budget"
        ordering = ['-sent_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'objectif', 'niveau', 'periode_cle'],
                name='uniq_budget_notification_period',
            ),
        ]

    def __str__(self):
        return f"{self.email_to} — {self.objectif} — {self.niveau}"


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
