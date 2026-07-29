from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0028_order_deadline_order_delivery_cost_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='basebreadingredient',
            name='unit',
        ),
        migrations.RemoveField(
            model_name='fillingingredient',
            name='unit',
        ),
        migrations.RemoveField(
            model_name='toppingingredient',
            name='unit',
        ),
    ]
