from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_objectif_categorie'),
    ]

    operations = [
        migrations.AddField(
            model_name='objectif',
            name='entreprise',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='objectifs',
                to='api.entreprise',
                verbose_name='Entreprise ciblée',
            ),
        ),
    ]
