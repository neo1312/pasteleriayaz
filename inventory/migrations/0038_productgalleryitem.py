from django.db import migrations, models


def seed_from_products(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')
    ProductGalleryItem = apps.get_model('inventory', 'ProductGalleryItem')

    products = (
        Product.objects.filter(show_in_gallery=True)
        .exclude(image='')
        .exclude(image__isnull=True)
        .order_by('name')
    )
    for index, product in enumerate(products):
        ProductGalleryItem.objects.create(
            name=product.name,
            description=product.short_description or product.description or '',
            image=product.image.name,
            is_active=True,
            featured=product.featured,
            sort_order=index,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0037_client_email_phone_optional'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductGalleryItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Nombre')),
                ('description', models.TextField(blank=True, verbose_name='Descripción')),
                ('image', models.ImageField(upload_to='gallery/', verbose_name='Imagen')),
                ('is_active', models.BooleanField(default=True, verbose_name='Visible en galería')),
                ('featured', models.BooleanField(default=False, verbose_name='Destacado')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Orden')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Creado')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Actualizado')),
            ],
            options={
                'verbose_name': 'Elemento de galería',
                'verbose_name_plural': 'Galería',
                'ordering': ['sort_order', '-created_at'],
            },
        ),
        migrations.RunPython(seed_from_products, migrations.RunPython.noop),
    ]
