from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from api.models import User, Entreprise, EntrepriseAccess, Transaction, Objectif
from api.views import invalidate_dashboard_cache


class APIFeaturesTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            email='admin@test.com',
            password='Admin123!',
            nom='Admin',
            role='admin',
            is_staff=True,
        )
        self.ent = Entreprise.objects.create(nom='Entreprise Test')

    def _auth(self, user):
        token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_admin_can_add_manual_revenu(self):
        self._auth(self.admin)
        url = '/api/transactions/ajouter-revenu/'
        payload = {
            'montant': '250.00',
            'label': 'Revenu manuel test',
            'categorie': 'vente',
            'entreprise': self.ent.id,
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Transaction.objects.count(), 1)
        txn = Transaction.objects.first()
        self.assertEqual(txn.type, 'revenu')
        self.assertEqual(txn.user, self.admin)

    def test_dashboard_returns_finance_indicators(self):
        Transaction.objects.create(
            type='revenu',
            categorie='vente',
            montant=Decimal('300.00'),
            label='Revenu test',
            entreprise=self.ent,
            user=self.admin,
        )
        Transaction.objects.create(
            type='depense',
            categorie='marketing',
            montant=Decimal('90.00'),
            label='Depense test',
            entreprise=self.ent,
            user=self.admin,
        )

        self._auth(self.admin)
        response = self.client.get('/api/dashboard/?periode=mois')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(response.data['revenus_total'])), Decimal('300.00'))
        self.assertEqual(Decimal(str(response.data['depenses_total'])), Decimal('90.00'))
        self.assertEqual(Decimal(str(response.data['benefice_net'])), Decimal('210.00'))
        self.assertEqual(response.data['nb_transactions'], 2)
        self.assertEqual(response.data['nb_revenus'], 1)
        self.assertEqual(response.data['nb_depenses'], 1)
        self.assertEqual(float(response.data['marge_nette_percent']), 70.0)
        self.assertEqual(len(response.data['transactions_recentes']), 2)

    def test_budget_alerts_returns_over_limit_objective(self):
        Objectif.objects.create(
            type='depense',
            montant=Decimal('50.00'),
            periode='mensuel',
            label='Budget test',
        )
        Transaction.objects.create(
            type='depense',
            montant=Decimal('80.00'),
            label='Depense test',
            entreprise=self.ent,
            user=self.admin,
        )
        self._auth(self.admin)
        response = self.client.get('/api/budget/alerts/?seuil=70')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data['count'], 1)

    def test_budget_alerts_filter_expenses_by_category(self):
        Objectif.objects.create(
            type='depense',
            categorie='marketing',
            montant=Decimal('50.00'),
            periode='mensuel',
            label='Budget marketing',
        )
        Transaction.objects.create(
            type='depense',
            categorie='salaire',
            montant=Decimal('80.00'),
            label='Salaire test',
            entreprise=self.ent,
            user=self.admin,
        )

        self._auth(self.admin)
        response = self.client.get('/api/budget/alerts/?seuil=70')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_revenue_objective_can_target_one_entreprise(self):
        other_ent = Entreprise.objects.create(nom='Autre entreprise')
        objectif = Objectif.objects.create(
            type='revenu',
            entreprise=self.ent,
            montant=Decimal('500.00'),
            periode='mensuel',
            label='Objectif entreprise',
        )
        Transaction.objects.create(
            type='revenu',
            categorie='vente',
            montant=Decimal('120.00'),
            label='Revenu cible',
            entreprise=self.ent,
            user=self.admin,
        )
        Transaction.objects.create(
            type='revenu',
            categorie='vente',
            montant=Decimal('300.00'),
            label='Revenu autre',
            entreprise=other_ent,
            user=self.admin,
        )

        self._auth(self.admin)
        response = self.client.get(f'/api/objectifs/{objectif.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['entreprise'], self.ent.id)
        self.assertEqual(response.data['entreprise_nom'], self.ent.nom)
        self.assertEqual(Decimal(str(response.data['progression']['total'])), Decimal('120.0'))

    def test_cannot_delete_entreprise_with_financial_transactions(self):
        Transaction.objects.create(
            type='revenu',
            montant=Decimal('300.00'),
            label='Revenu protege',
            entreprise=self.ent,
            user=self.admin,
        )

        self._auth(self.admin)
        response = self.client.delete(f'/api/entreprises/{self.ent.id}/')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Entreprise.objects.filter(id=self.ent.id).exists())
        self.assertEqual(Transaction.objects.filter(entreprise=self.ent).count(), 1)

    def test_staff_admin_dashboard_stays_global_after_creating_entreprise(self):
        Transaction.objects.create(
            type='revenu',
            montant=Decimal('300.00'),
            label='Revenu existant',
            entreprise=self.ent,
            user=self.admin,
        )
        Transaction.objects.create(
            type='depense',
            montant=Decimal('50.00'),
            label='Depense existante',
            entreprise=self.ent,
            user=self.admin,
        )
        self._auth(self.admin)

        before = self.client.get('/api/dashboard/?periode=mois')
        self.assertEqual(before.status_code, status.HTTP_200_OK)
        rev_before = Decimal(str(before.data['revenus_total']))
        dep_before = Decimal(str(before.data['depenses_total']))

        create_response = self.client.post('/api/entreprises/', {'nom': 'Nouvelle Entreprise'}, format='json')
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(EntrepriseAccess.objects.filter(user=self.admin).count(), 0)

        after = self.client.get('/api/dashboard/?periode=mois')
        self.assertEqual(after.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(after.data['revenus_total'])), rev_before)
        self.assertEqual(Decimal(str(after.data['depenses_total'])), dep_before)

    def test_scoped_admin_remains_scoped_and_gets_access_on_created_entreprise(self):
        scoped_admin = User.objects.create_user(
            email='scoped-admin@test.com',
            password='Admin123!',
            nom='Scoped Admin',
            role='admin',
            is_staff=False,
        )
        ent_scoped = Entreprise.objects.create(nom='Scoped Ent')
        ent_hidden = Entreprise.objects.create(nom='Hidden Ent')
        EntrepriseAccess.objects.create(user=scoped_admin, entreprise=ent_scoped)

        Transaction.objects.create(
            type='revenu',
            montant=Decimal('120.00'),
            label='Scoped revenu',
            entreprise=ent_scoped,
            user=scoped_admin,
        )
        Transaction.objects.create(
            type='revenu',
            montant=Decimal('999.00'),
            label='Hidden revenu',
            entreprise=ent_hidden,
            user=scoped_admin,
        )

        self._auth(scoped_admin)
        before = self.client.get('/api/dashboard/?periode=mois')
        self.assertEqual(before.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(before.data['revenus_total'])), Decimal('120.00'))

        create_response = self.client.post('/api/entreprises/', {'nom': 'Scoped New Ent'}, format='json')
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        new_ent_id = create_response.data['id']
        self.assertTrue(EntrepriseAccess.objects.filter(user=scoped_admin, entreprise_id=new_ent_id).exists())

        after = self.client.get('/api/dashboard/?periode=mois')
        self.assertEqual(after.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(after.data['revenus_total'])), Decimal('120.00'))

    def test_scoped_admin_without_access_does_not_become_global(self):
        scoped_admin = User.objects.create_user(
            email='no-access-admin@test.com',
            password='Admin123!',
            nom='No Access Admin',
            role='admin',
            is_staff=False,
        )
        Transaction.objects.create(
            type='revenu',
            montant=Decimal('500.00'),
            label='Should stay hidden',
            entreprise=self.ent,
            user=self.admin,
        )

        self._auth(scoped_admin)
        response = self.client.get('/api/dashboard/?periode=mois')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(response.data['revenus_total'])), Decimal('0'))
        self.assertEqual(response.data['nb_transactions'], 0)

    def test_scoped_admin_cannot_create_transaction_outside_scope(self):
        scoped_admin = User.objects.create_user(
            email='blocked-admin@test.com',
            password='Admin123!',
            nom='Blocked Admin',
            role='admin',
            is_staff=False,
        )
        visible_ent = Entreprise.objects.create(nom='Visible Ent')
        EntrepriseAccess.objects.create(user=scoped_admin, entreprise=visible_ent)

        self._auth(scoped_admin)
        response = self.client.post(
            '/api/transactions/',
            {
                'type': 'revenu',
                'categorie': 'vente',
                'montant': '120.00',
                'label': 'Hors scope',
                'entreprise': self.ent.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_created_with_entreprise_ids_is_scoped(self):
        hidden_ent = Entreprise.objects.create(nom='Hidden Ent For API Admin')
        Transaction.objects.create(
            type='revenu',
            montant=Decimal('120.00'),
            label='Visible revenu',
            entreprise=self.ent,
            user=self.admin,
        )
        Transaction.objects.create(
            type='revenu',
            montant=Decimal('999.00'),
            label='Hidden revenu',
            entreprise=hidden_ent,
            user=self.admin,
        )

        self._auth(self.admin)
        create_response = self.client.post(
            '/api/users/',
            {
                'nom': 'Scoped API Admin',
                'email': 'scoped-api-admin@test.com',
                'password': 'Admin123!',
                'role': 'admin',
                'entreprise_ids': [self.ent.id],
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        scoped_admin = User.objects.get(email='scoped-api-admin@test.com')
        self.assertFalse(scoped_admin.is_staff)
        self.assertTrue(
            EntrepriseAccess.objects.filter(user=scoped_admin, entreprise=self.ent).exists()
        )

        self._auth(scoped_admin)
        dashboard_response = self.client.get('/api/dashboard/?periode=mois')

        self.assertEqual(dashboard_response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(dashboard_response.data['revenus_total'])), Decimal('120.00'))

    def test_dashboard_cache_invalidation_keeps_unrelated_cache(self):
        cache.set('unrelated-cache-key', 'keep-me', timeout=60)

        invalidate_dashboard_cache()

        self.assertEqual(cache.get('unrelated-cache-key'), 'keep-me')

    @patch('api.realtime.get_channel_layer')
    def test_create_entreprise_still_succeeds_if_realtime_broadcast_fails(self, mock_get_channel_layer):
        class BrokenChannelLayer:
            async def group_send(self, *args, **kwargs):
                raise RuntimeError('channel layer unavailable')

        mock_get_channel_layer.return_value = BrokenChannelLayer()

        self._auth(self.admin)
        response = self.client.post('/api/entreprises/', {'nom': 'Entreprise Sans WS'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Entreprise.objects.filter(nom='Entreprise Sans WS').exists())
