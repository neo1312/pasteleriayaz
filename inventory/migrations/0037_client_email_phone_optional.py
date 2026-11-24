from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0036_remove_quote_show_delivery_on_pdf'),
    ]

    operations = [
        migrations.AlterField(
            model_name='client',
            name='email',
            field=models.EmailField(blank=True, max_length=254, verbose_name='Email'),
        ),
        migrations.AlterField(
            model_name='client',
            name='phone',
            field=models.CharField(blank=True, max_length=20, verbose_name='Teléfono'),
        ),
    ]
