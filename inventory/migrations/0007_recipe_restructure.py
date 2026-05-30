from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0006_recipeingredient_alter_product_ingredients'),
    ]

    operations = [
        # Remove old M2M ingredients from Product
        migrations.RemoveField(
            model_name='product',
            name='ingredients',
        ),
        # Remove old RecipeIngredient (was linked to Product)
        migrations.DeleteModel(
            name='RecipeIngredient',
        ),
        # Create Recipe model
        migrations.CreateModel(
            name='Recipe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name_plural': 'Recipes',
                'ordering': ['name'],
            },
        ),
        # Create new RecipeIngredient linked to Recipe
        migrations.CreateModel(
            name='RecipeIngredient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.DecimalField(decimal_places=3, help_text='Amount needed', max_digits=10)),
                ('unit', models.CharField(choices=[('g', 'Grams'), ('mg', 'Milligrams'), ('pcs', 'Pieces')], default='g', max_length=5)),
                ('notes', models.CharField(blank=True, help_text="Optional note, e.g. 'sifted', 'melted'", max_length=200)),
                ('recipe', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ingredients', to='inventory.recipe')),
                ('raw_product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recipe_uses', to='inventory.rawproduct', verbose_name='Raw Product')),
            ],
            options={
                'verbose_name': 'Ingredient',
                'verbose_name_plural': 'Ingredients',
                'unique_together': {('recipe', 'raw_product')},
            },
        ),
        # Add recipe FK to Product
        migrations.AddField(
            model_name='product',
            name='recipe',
            field=models.OneToOneField(blank=True, help_text='Recipe used to make this product', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='product', to='inventory.recipe'),
        ),
    ]
