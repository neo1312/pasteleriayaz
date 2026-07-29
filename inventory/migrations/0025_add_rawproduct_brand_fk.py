import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0024_rename_rawproduct_brand_to_old_brand'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='rawproduct',
            options={'ordering': ['name', 'brand__name', 'old_brand'], 'verbose_name': 'Materia Prima', 'verbose_name_plural': 'Materias Primas'},
        ),
        migrations.AddField(
            model_name='rawproduct',
            name='brand',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='inventory.brand', verbose_name='Marca'),
        ),
    ]
