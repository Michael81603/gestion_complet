from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from api.models import User, Entreprise, EntrepriseAccess, Commande, Transaction, Objectif


class APIFeaturesTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@test.com',
            password='Admin123!',
            nom='Admin',
            role='admin',
            is_staff=True,
        )
        self.livreur = User.objects.create_user(
            email='livreur@test.com',
            password='Livreur123!',
            nom='Livreur One',
            role='livreur',
        )
        self.other_livreur = User.objects.create_user(
            email='livreur2@test.com',
            password='Livreur123!',
            nom='Livreur Two',
            role='livreur',
        )
        self.ent = Entreprise.objects.create(nom='Entreprise Test')
        self.commande = Commande.objects.create(
            entreprise=self.ent,
            livreur=self.livreur,
            client_nom='Client',
            adresse='Adresse',
            prix=Decimal('100.00'),
            cout_livraison=Decimal('10.00'),
            statut='en attente',
        )

    def _auth(self, user):
        token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_livreur_can_demarrer_own_commande(self):
        self._auth(self.livreur)
        url = f'/api/commandes/{self.commande.id}/demarrer/'
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.statut, 'en cours')
        self.assertIsNotNone(self.commande.date_demarrage)

    def test_livreur_cannot_demarrer_other_commande(self):
        self._auth(self.other_livreur)
        url = f'/api/commandes/{self.commande.id}/demarrer/'
        response = self.client.post(url)
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_admin_can_add_manual_revenu(self):
        self._auth(self.admin)
        url = '/api/transactions/ajouter-revenu/'
        payload = {
            'montant': '250.00',
            'label': 'Revenu manuel test',
            'entreprise': self.ent.id,
            'user': self.livreur.id,
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Transaction.objects.count(), 1)
        txn = Transaction.objects.first()
        self.assertEqual(txn.type, 'revenu')

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
