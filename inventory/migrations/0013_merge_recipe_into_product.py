"""
Merge the Recipe model into Product:
  1. Add nullable product FK to RecipeIngredient
  2. Populate it from the Recipe → Product OneToOne link
  3. Make it non-nullable
  4. Update unique_together
  5. Drop recipe FK from RecipeIngredient
  6. Drop recipe FK from Product
  7. Delete Recipe model
"""
from django.db import migrations, models
import django.db.models.deletion


def populate_product_from_recipe(apps, schema_editor):
    # Delete orphaned ingredients (recipes with no linked product)
    schema_editor.execute("""
        DELETE FROM inventory_recipeingredient
        WHERE recipe_id NOT IN (
            SELECT recipe_id FROM inventory_product WHERE recipe_id IS NOT NULL
        )
    """)
    # Set product_id via the recipe → product OneToOne
    schema_editor.execute("""
        UPDATE inventory_recipeingredient
        SET product_id = (
            SELECT id FROM inventory_product
            WHERE inventory_product.recipe_id = inventory_recipeingredient.recipe_id
        )
        WHERE recipe_id IS NOT NULL
    """)


def reverse_populate(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0012_pricing_mode'),
    ]

    operations = [
        # 1. Add product FK (nullable so data migration can populate it)
        migrations.AddField(
            model_name='recipeingredient',
            name='product',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='ingredients',
                to='inventory.product',
                verbose_name='Product',
            ),
        ),

        # 2. Populate from existing Recipe → Product link
        migrations.RunPython(populate_product_from_recipe, reverse_populate),

        # 3. Make product non-nullable
        migrations.AlterField(
            model_name='recipeingredient',
            name='product',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='ingredients',
                to='inventory.product',
                verbose_name='Product',
            ),
        ),

        # 4. Swap unique_together to use product instead of recipe
        migrations.AlterUniqueTogether(
            name='recipeingredient',
            unique_together={('product', 'raw_product')},
        ),

        # 5. Drop recipe FK from RecipeIngredient
        migrations.RemoveField(
            model_name='recipeingredient',
            name='recipe',
        ),

        # 6. Drop recipe FK from Product
        migrations.RemoveField(
            model_name='product',
            name='recipe',
        ),

        # 7. Delete Recipe model
        migrations.DeleteModel(
            name='Recipe',
        ),
    ]
