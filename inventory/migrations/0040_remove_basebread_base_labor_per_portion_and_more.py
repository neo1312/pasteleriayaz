from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0039_productgalleryitem_tags'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='basebread',
            name='base_labor_per_portion',
        ),
        migrations.RemoveField(
            model_name='topping',
            name='base_labor_per_portion',
        ),
    ]
