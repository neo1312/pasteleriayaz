from django.db import migrations, models


def copy_product_tags(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')
    ProductGalleryItem = apps.get_model('inventory', 'ProductGalleryItem')

    for item in ProductGalleryItem.objects.all():
        product = (
            Product.objects.filter(name=item.name)
            .exclude(event_tags__isnull=True)
            .first()
        )
        if product:
            item.tags.set(product.event_tags.all())


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0038_productgalleryitem'),
    ]

    operations = [
        migrations.AddField(
            model_name='productgalleryitem',
            name='tags',
            field=models.ManyToManyField(blank=True, to='inventory.eventtag', verbose_name='Etiquetas'),
        ),
        migrations.RunPython(copy_product_tags, migrations.RunPython.noop),
    ]
