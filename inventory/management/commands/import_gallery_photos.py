import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from inventory.image_utils import optimize_image, GALLERY_WIDTH, GALLERY_HEIGHT
from inventory.models import ProductGalleryItem


class Command(BaseCommand):
    help = 'Recorta (3:4) y optimiza imágenes a WebP de un directorio y crea elementos de galería.'

    def add_arguments(self, parser):
        parser.add_argument('src_dir', type=str, help='Directorio con las imágenes fuente')
        parser.add_argument('--prefix', default='Pastel de catálogo', help='Prefijo del nombre de cada elemento')
        parser.add_argument('--description', default='Pastel artesanal', help='Descripción de cada elemento')

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

        gallery_dir = Path(settings.MEDIA_ROOT) / 'gallery'
        gallery_dir.mkdir(parents=True, exist_ok=True)

        created = 0
        for index, src in enumerate(images, start=1):
            data, filename = optimize_image(
                str(src),
                target_size=(GALLERY_WIDTH, GALLERY_HEIGHT),
            )
            dest = gallery_dir / filename

            rel_path = f'gallery/{filename}'
            if ProductGalleryItem.objects.filter(image=rel_path).exists():
                self.stdout.write(f'  Omitido (ya importado): {filename}')
                continue

            dest.write_bytes(data)
            name = f"{opts['prefix']} {index}"
            ProductGalleryItem.objects.create(
                name=name,
                description=opts['description'],
                image=rel_path,
                is_active=True,
                sort_order=index,
            )
            size_kb = round(len(data) / 1024, 1)
            self.stdout.write(self.style.SUCCESS(
                f'  ✓ Creado "{name}" -> {filename} ({size_kb} KB)'
            ))
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Listo. {created} elemento(s) creado(s) en {gallery_dir}.'
        ))
