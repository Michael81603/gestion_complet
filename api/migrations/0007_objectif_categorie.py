from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_objectif_date_debut_objectif_date_fin_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='objectif',
            name='categorie',
            field=models.CharField(
                blank=True,
                choices=[
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
                ],
                max_length=20,
                null=True,
                verbose_name='Catégorie de dépense',
            ),
        ),
    ]
