from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0022_brand_product_brand'),
    ]

    operations = [
        migrations.RunSQL(
            """
            CREATE TABLE "new__inventory_rawproduct" (
                "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                "old_brand" VARCHAR(200) NOT NULL DEFAULT '',
                "name" VARCHAR(200) NOT NULL,
                "description" TEXT NOT NULL,
                "unit" VARCHAR(20) NOT NULL,
                "cost_per_unit" DECIMAL NOT NULL,
                "quantity_in_stock" DECIMAL NOT NULL,
                "reorder_level" DECIMAL NOT NULL,
                "created_at" DATETIME NOT NULL,
                "updated_at" DATETIME NOT NULL,
                "provider_id" BIGINT NULL REFERENCES "inventory_provider" ("id") DEFERRABLE INITIALLY DEFERRED,
                "average_cost" DECIMAL NOT NULL
            );
            INSERT INTO "new__inventory_rawproduct" (
                "id", "old_brand", "name", "description", "unit", "cost_per_unit",
                "quantity_in_stock", "reorder_level", "created_at", "updated_at",
                "provider_id", "average_cost"
            )
            SELECT
                "id", "brand", "name", "description", "unit", "cost_per_unit",
                "quantity_in_stock", "reorder_level", "created_at", "updated_at",
                "provider_id", "average_cost"
            FROM "inventory_rawproduct";
            DROP TABLE "inventory_rawproduct";
            ALTER TABLE "new__inventory_rawproduct" RENAME TO "inventory_rawproduct";
            CREATE INDEX "inventory_rawproduct_provider_id_6367ddb8" ON "inventory_rawproduct" ("provider_id");
            """,
            reverse_sql="""
            CREATE TABLE "new__inventory_rawproduct" (
                "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                "brand" VARCHAR(200) NOT NULL DEFAULT '',
                "name" VARCHAR(200) NOT NULL,
                "description" TEXT NOT NULL,
                "unit" VARCHAR(20) NOT NULL,
                "cost_per_unit" DECIMAL NOT NULL,
                "quantity_in_stock" DECIMAL NOT NULL,
                "reorder_level" DECIMAL NOT NULL,
                "created_at" DATETIME NOT NULL,
                "updated_at" DATETIME NOT NULL,
                "provider_id" BIGINT NULL REFERENCES "inventory_provider" ("id") DEFERRABLE INITIALLY DEFERRED,
                "average_cost" DECIMAL NOT NULL
            );
            INSERT INTO "new__inventory_rawproduct" (
                "id", "brand", "name", "description", "unit", "cost_per_unit",
                "quantity_in_stock", "reorder_level", "created_at", "updated_at",
                "provider_id", "average_cost"
            )
            SELECT
                "id", "old_brand", "name", "description", "unit", "cost_per_unit",
                "quantity_in_stock", "reorder_level", "created_at", "updated_at",
                "provider_id", "average_cost"
            FROM "inventory_rawproduct";
            DROP TABLE "inventory_rawproduct";
            ALTER TABLE "new__inventory_rawproduct" RENAME TO "inventory_rawproduct";
            CREATE INDEX "inventory_rawproduct_provider_id_6367ddb8" ON "inventory_rawproduct" ("provider_id");
            """,
        ),
    ]
