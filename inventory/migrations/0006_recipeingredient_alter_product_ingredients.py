from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0005_product_ingredients'),
    ]

    operations = [
        # Step 1: Remove the existing plain M2M field (drops the auto-created join table)
        migrations.RemoveField(
            model_name='product',
            name='ingredients',
        ),
        # Step 2: Create the through model table
        migrations.CreateModel(
            name='RecipeIngredient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.DecimalField(decimal_places=3, help_text='Amount needed', max_digits=10)),
                ('unit', models.CharField(choices=[('g', 'Grams'), ('mg', 'Milligrams'), ('pcs', 'Pieces')], default='g', max_length=5)),
                ('notes', models.CharField(blank=True, help_text="Optional note, e.g. 'sifted', 'melted'", max_length=200)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recipe_ingredients', to='inventory.product')),
                ('raw_product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recipe_uses', to='inventory.rawproduct', verbose_name='Ingredient')),
            ],
            options={
                'verbose_name': 'Recipe Ingredient',
                'verbose_name_plural': 'Recipe Ingredients',
                'unique_together': {('product', 'raw_product')},
            },
        ),
        # Step 3: Re-add ingredients as M2M with through model
        migrations.AddField(
            model_name='product',
            name='ingredients',
            field=models.ManyToManyField(blank=True, help_text='Ingredients used in this product', related_name='used_in_products', through='inventory.RecipeIngredient', to='inventory.rawproduct'),
        ),
    ]
