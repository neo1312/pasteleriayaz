import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from inventory.image_utils import optimize_image
from inventory.models import Product


class Command(BaseCommand):
    help = 'Optimiza imágenes (WebP ~800px) de un directorio y crea productos de galería.'

    def add_arguments(self, parser):
        parser.add_argument('src_dir', type=str, help='Directorio con las imágenes fuente')
        parser.add_argument('--prefix', default='Pastel de catálogo', help='Prefijo del nombre de cada producto')
        parser.add_argument('--category', default='cake', help='Categoría del producto')

    def handle(self, *args, **opts):
        src_dir = Path(opts['src_dir'])
        if not src_dir.is_dir():
            raise CommandError(f'El directorio no existe: {src_dir}')

        extensions = {'.jpg', '.jpeg', '.png', '.webp'}
        images = sorted(
            p for p in src_dir.iterdir()
            if p.is_file() and p.suffix.lower() in extensions
        )
        if not images:
            raise CommandError('No se encontraron imágenes en el directorio.')

        products_dir = Path(settings.MEDIA_ROOT) / 'products'
        products_dir.mkdir(parents=True, exist_ok=True)

        created = 0
        for index, src in enumerate(images, start=1):
            data, filename = optimize_image(str(src))
            dest = products_dir / filename

            rel_path = f'products/{filename}'
            if Product.objects.filter(image=rel_path).exists():
                self.stdout.write(f'  Omitido (ya importado): {filename}')
                continue

            dest.write_bytes(data)
            name = f"{opts['prefix']} {index}"
            Product.objects.create(
                name=name,
                category=opts['category'],
                short_description='Pastel artesanal',
                is_available=True,
                show_in_gallery=True,
                image=rel_path,
            )
            size_kb = round(len(data) / 1024, 1)
            self.stdout.write(self.style.SUCCESS(
                f'  ✓ Creado "{name}" -> {filename} ({size_kb} KB)'
            ))
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Listo. {created} producto(s) creado(s) en {products_dir}.'
        ))
