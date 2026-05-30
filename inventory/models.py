from django.db import models
from decimal import Decimal


# Conversion factors to normalize ingredient units → raw product units
_UNIT_FACTORS = {
    ('mg', 'mg'): Decimal('1'),
    ('mg', 'g'):  Decimal('0.001'),
    ('mg', 'kg'): Decimal('0.000001'),
    ('g',  'mg'): Decimal('1000'),
    ('g',  'g'):  Decimal('1'),
    ('g',  'kg'): Decimal('0.001'),
    ('kg', 'mg'): Decimal('1000000'),
    ('kg', 'g'):  Decimal('1000'),
    ('kg', 'kg'): Decimal('1'),
    ('pcs', 'pcs'):   Decimal('1'),
    ('pcs', 'unit'):  Decimal('1'),
    ('pcs', 'dozen'): Decimal('0.083333'),
    ('pcs', 'box'):   Decimal('1'),
}


def _conversion_factor(from_unit, to_unit):
    if from_unit == to_unit:
        return Decimal('1')
    return _UNIT_FACTORS.get((from_unit, to_unit), Decimal('1'))


class Product(models.Model):
    CATEGORY_CHOICES = [
        ('bread', 'Pan'),
        ('cake', 'Pastel'),
        ('pastry', 'Pastelería'),
        ('cookie', 'Galleta'),
        ('donut', 'Dona'),
        ('other', 'Otro'),
    ]
    PRICING_MODE_CHOICES = [
        ('margin', 'Establecer margen → precio auto-calculado'),
        ('price',  'Establecer precio → margen auto-calculado'),
    ]

    name = models.CharField(max_length=200, verbose_name="Nombre")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, verbose_name="Categoría")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")
    short_description = models.CharField(max_length=300, blank=True, null=True, help_text="Descripción corta para galería", verbose_name="Descripción corta")
    cost = models.DecimalField(max_digits=16, decimal_places=6, default=0, help_text="Costo de producción (auto desde ingredientes)", verbose_name="Costo")
    pricing_mode = models.CharField(
        max_length=10,
        choices=PRICING_MODE_CHOICES,
        default='margin',
        help_text="Elige qué ingresarás; el otro valor se calcula automáticamente.",
        verbose_name="Modo de precios"
    )
    price = models.DecimalField(max_digits=16, decimal_places=6, default=0, verbose_name="Precio")
    margin_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=30, help_text="Porcentaje de ganancia", verbose_name="Margen %")
    quantity_in_stock = models.IntegerField(default=0, verbose_name="Cantidad en stock")
    reorder_level = models.IntegerField(default=5, verbose_name="Nivel de reorden")
    image = models.ImageField(upload_to='products/', blank=True, null=True, verbose_name="Imagen")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado")
    is_available = models.BooleanField(default=True, verbose_name="Disponible")

    def calculate_cost(self):
        """Sum ingredient costs using each raw product's weighted average cost."""
        total = Decimal('0')
        for ing in self.ingredients.select_related('raw_product'):
            rp = ing.raw_product
            unit_cost = rp.average_cost if rp.average_cost else rp.cost_per_unit
            factor = _conversion_factor(ing.unit, rp.unit)
            total += ing.quantity * factor * unit_cost
        return total

    def calculate_margin(self):
        if self.cost > 0:
            return ((self.price - self.cost) / self.cost) * 100
        return 0

    def check_stock_for(self, order_quantity):
        """
        Returns a list of shortage dicts for producing `order_quantity` units.
        Empty list means all materials are available.
        """
        shortages = []
        for ing in self.ingredients.select_related('raw_product'):
            rp = ing.raw_product
            needed = ing.quantity * _conversion_factor(ing.unit, rp.unit) * Decimal(str(order_quantity))
            if needed > (rp.quantity_in_stock or Decimal('0')):
                shortages.append({
                    'name':      rp.name,
                    'needed':    needed,
                    'available': rp.quantity_in_stock or Decimal('0'),
                    'unit':      rp.unit,
                    'shortage':  needed - (rp.quantity_in_stock or Decimal('0')),
                })
        return shortages

    def __str__(self):
        return f"{self.name} ({self.quantity_in_stock} in stock)"

    class Meta:
        ordering = ['name']
        verbose_name_plural = "Products"


class Client(models.Model):
    name = models.CharField(max_length=200, verbose_name="Nombre")
    email = models.EmailField(verbose_name="Email")
    phone = models.CharField(max_length=20, verbose_name="Teléfono")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado")

    def __str__(self):
        return f"{self.name} ({self.email})"

    class Meta:
        ordering = ['name']
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('completed', 'Completado'),
        ('cancelled', 'Cancelado'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='orders', verbose_name="Cliente")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='orders', verbose_name="Producto")
    quantity = models.IntegerField(default=1, verbose_name="Cantidad")
    unit_price = models.DecimalField(max_digits=16, decimal_places=6, default=0, help_text="Precio por unidad", verbose_name="Precio unitario")
    total_price = models.DecimalField(max_digits=16, decimal_places=6, verbose_name="Precio total")
    order_date = models.DateTimeField(auto_now_add=True, verbose_name="Fecha del pedido")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Estado")
    notes = models.TextField(blank=True, null=True, verbose_name="Notas")

    def save(self, *args, **kwargs):
        # Auto-populate unit_price from product price if not set
        if self.product and (not self.unit_price or self.unit_price == 0):
            self.unit_price = self.product.price
        
        # Auto-calculate total_price from unit_price and quantity
        if self.unit_price and self.quantity:
            self.total_price = (self.unit_price * Decimal(str(self.quantity))).quantize(Decimal('0.000001'))
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Pedido #{self.id} - {self.client.name} ({self.status})"

    class Meta:
        ordering = ['-order_date']
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"


class Provider(models.Model):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=200, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.contact_person})"

    class Meta:
        ordering = ['name']


class RawProduct(models.Model):
    UNIT_CHOICES = [
        ('kg', 'Kilogram'),
        ('g', 'Gram'),
        ('l', 'Liter'),
        ('ml', 'Milliliter'),
        ('unit', 'Unit'),
        ('box', 'Box'),
        ('dozen', 'Dozen'),
    ]

    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=200, blank=True, help_text="Brand or manufacturer")
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='kg')
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=6, verbose_name="Last Cost", help_text="Cost from most recent purchase", default=0)
    average_cost = models.DecimalField(max_digits=10, decimal_places=6, default=0, help_text="Weighted average cost across all purchases")
    quantity_in_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=10)
    provider = models.ForeignKey(Provider, on_delete=models.SET_NULL, null=True, blank=True, related_name='raw_products')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        brand_str = f" [{self.brand}]" if self.brand else ""
        return f"{self.name}{brand_str} ({self.quantity_in_stock} {self.unit})"

    class Meta:
        ordering = ['name', 'brand']
        verbose_name_plural = "Raw Products"


class ProviderCatalog(models.Model):
    """Records the current/latest price a provider offers for a raw product."""
    raw_product  = models.ForeignKey(RawProduct, on_delete=models.CASCADE, related_name='provider_prices')
    provider     = models.ForeignKey(Provider,   on_delete=models.CASCADE, related_name='catalog_prices')
    unit_price   = models.DecimalField(max_digits=16, decimal_places=6, help_text="Price per unit offered by this provider")
    notes        = models.CharField(max_length=300, blank=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('raw_product', 'provider')
        ordering = ['unit_price']
        verbose_name = "Provider Price"
        verbose_name_plural = "Provider Prices"

    def __str__(self):
        return f"{self.provider.name} → {self.raw_product.name}: ${self.unit_price}"


class Purchase(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]

    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, related_name='purchases')
    purchase_date = models.DateTimeField(auto_now_add=True)
    delivery_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)

    @property
    def total_cost(self):
        return sum(item.item_total for item in self.items.all())

    def __str__(self):
        return f"Purchase #{self.id} – {self.provider.name} ({self.status})"

    class Meta:
        ordering = ['-purchase_date']
        verbose_name_plural = "Purchases"


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='items')
    raw_product = models.ForeignKey(RawProduct, on_delete=models.PROTECT, related_name='purchase_items', verbose_name="Raw Product")
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=16, decimal_places=6, help_text="Cost per unit")
    item_total = models.DecimalField(max_digits=16, decimal_places=6, editable=False, default=0)

    def save(self, *args, **kwargs):
        self.item_total = self.quantity * self.unit_cost
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.raw_product.name} x{self.quantity}"

    class Meta:
        verbose_name = "Purchase Item"
        verbose_name_plural = "Purchase Items"


class RecipeIngredient(models.Model):
    UNIT_CHOICES = [
        ('g', 'Grams'),
        ('mg', 'Milligrams'),
        ('pcs', 'Pieces'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='ingredients', verbose_name="Product")
    raw_product = models.ForeignKey(RawProduct, on_delete=models.CASCADE, related_name='recipe_uses', verbose_name="Raw Product")
    quantity = models.DecimalField(max_digits=10, decimal_places=3, help_text="Amount needed")
    unit = models.CharField(max_length=5, choices=UNIT_CHOICES, default='g')
    notes = models.CharField(max_length=200, blank=True, help_text="Optional note, e.g. 'sifted', 'melted'")

    def __str__(self):
        return f"{self.quantity} {self.get_unit_display()} of {self.raw_product.name}"

    class Meta:
        unique_together = ('product', 'raw_product')
        verbose_name = "Ingredient"
        verbose_name_plural = "Ingredients"


class Quote(models.Model):
    STATUS_CHOICES = [
        ('draft',    'Draft'),
        ('sent',     'Sent'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('expired',  'Expired'),
    ]

    client        = models.ForeignKey(Client,  on_delete=models.CASCADE, related_name='quotes')
    product       = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='quotes')
    quantity      = models.PositiveIntegerField(default=1)
    unit_price    = models.DecimalField(max_digits=16, decimal_places=6, default=0, help_text="Price per unit (auto-filled from product)")
    delivery_cost = models.DecimalField(max_digits=16, decimal_places=6, default=0)
    due_date      = models.DateField()
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes         = models.TextField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    @property
    def total_price(self):
        return (self.unit_price or Decimal('0')) * self.quantity

    @property
    def grand_total(self):
        return self.total_price + (self.delivery_cost or Decimal('0'))

    @property
    def days_until_due(self):
        from django.utils import timezone
        return (self.due_date - timezone.now().date()).days

    def __str__(self):
        return f"Quote #{self.id} – {self.client.name} ({self.product.name} × {self.quantity})"

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Quotes"
