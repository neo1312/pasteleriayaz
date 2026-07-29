from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0022_brand_product_brand'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='rawproduct',
            options={'ordering': ['name', 'old_brand'], 'verbose_name': 'Materia Prima', 'verbose_name_plural': 'Materias Primas'},
        ),
        migrations.RenameField(
            model_name='rawproduct',
            old_name='brand',
            new_name='old_brand',
        ),
    ]
