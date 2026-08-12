from django.db import models
from django.conf import settings
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


def calculate_components_cost(base_bread, filling, topping, complexity_tier, persons, benefit_percentage, extras_total=Decimal('0')):
    """Desglose de costos para un pastel armado por componentes (incluye beneficio).

    El beneficio se aplica sobre ingredientes + mano de obra + recargo de diseño
    + agregados. El envío nunca entra en esta base.
    Returns totals for all ``persons`` plus the unit price per person.
    """
    persons = Decimal(str(persons))
    pct = Decimal('100')
    ing_per = Decimal('0')
    labor_per = Decimal('0')
    if base_bread:
        ing_per += base_bread.cost_per_portion()
        labor_per += base_bread.base_labor_per_portion or Decimal('0')
    if filling:
        ing_per += filling.cost_per_portion()
        labor_per += filling.base_labor_per_portion or Decimal('0')
    if topping:
        ing_per += topping.cost_per_portion()
        labor_per += topping.base_labor_per_portion or Decimal('0')

    base_per = ing_per + labor_per
    design_pct = complexity_tier.surcharge_percentage if complexity_tier else Decimal('0')
    design_per = base_per * design_pct / pct
    comp_total = (base_per + design_per) * persons
    extras_total = Decimal(extras_total or '0')
    benefit_amount = (comp_total + extras_total) * (benefit_percentage or Decimal('0')) / pct
    total = comp_total + extras_total + benefit_amount

    return {
        'ingredient_cost': ing_per * persons,
        'labor_cost': labor_per * persons,
        'design_surcharge': design_per * persons,
        'benefit_amount': benefit_amount,
        'unit_price': (comp_total + benefit_amount) / persons if persons > 0 else Decimal('0'),
        'total': total,
    }


class ComplexityTier(models.Model):
    name = models.CharField(max_length=50, verbose_name="Nombre")
    surcharge_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Recargo %")
    description = models.TextField(blank=True, verbose_name="Descripción")

    class Meta:
        ordering = ['surcharge_percentage']
        verbose_name = "Nivel de Complejidad"
        verbose_name_plural = "Niveles de Complejidad"

    def __str__(self):
        return f"{self.name} (+{self.surcharge_percentage}%)"


class TransportZone(models.Model):
    name = models.CharField(max_length=100, verbose_name="Nombre")
    radius_km = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name="Radio (km)")
    base_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Tarifa base")
    fee_per_km = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Tarifa por km")

    class Meta:
        verbose_name = "Zona de Transporte"
        verbose_name_plural = "Zonas de Transporte"

    def __str__(self):
        return f"{self.name} (${self.base_fee} + ${self.fee_per_km}/km)"


class BaseBread(models.Model):
    name = models.CharField(max_length=200, verbose_name="Nombre")
    description = models.TextField(blank=True, verbose_name="Descripción")
    base_labor_per_portion = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Mano de obra + overhead por porción (1 persona)", verbose_name="Mano de obra por porción")
    is_available = models.BooleanField(default=True, verbose_name="Disponible")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado")

    def cost_per_portion(self):
        total = Decimal('0')
        for ing in self.ingredients.select_related('raw_product'):
            rp = ing.raw_product
            unit_cost = rp.average_cost if rp.average_cost else rp.cost_per_unit
            factor = _conversion_factor(ing.unit, rp.unit)
            total += ing.quantity * factor * unit_cost
        return total

    @property
    def total_cost_per_portion(self):
        return self.cost_per_portion() + (self.base_labor_per_portion or Decimal('0'))

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name = "Base de Pastel"
        verbose_name_plural = "Bases de Pastel"


class Filling(models.Model):
    name = models.CharField(max_length=200, verbose_name="Nombre")
    description = models.TextField(blank=True, verbose_name="Descripción")
    base_labor_per_portion = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Mano de obra + overhead por porción (1 persona)", verbose_name="Mano de obra por porción")
    is_available = models.BooleanField(default=True, verbose_name="Disponible")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado")

    def cost_per_portion(self):
        total = Decimal('0')
        for ing in self.ingredients.select_related('raw_product'):
            rp = ing.raw_product
            unit_cost = rp.average_cost if rp.average_cost else rp.cost_per_unit
            factor = _conversion_factor(ing.unit, rp.unit)
            total += ing.quantity * factor * unit_cost
        return total

    @property
    def total_cost_per_portion(self):
        return self.cost_per_portion() + (self.base_labor_per_portion or Decimal('0'))

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name = "Relleno"
        verbose_name_plural = "Rellenos"


class Topping(models.Model):
    name = models.CharField(max_length=200, verbose_name="Nombre")
    description = models.TextField(blank=True, verbose_name="Descripción")
    base_labor_per_portion = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Mano de obra + overhead por porción (1 persona)", verbose_name="Mano de obra por porción")
    is_available = models.BooleanField(default=True, verbose_name="Disponible")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado")

    def cost_per_portion(self):
        total = Decimal('0')
        for ing in self.ingredients.select_related('raw_product'):
            rp = ing.raw_product
            unit_cost = rp.average_cost if rp.average_cost else rp.cost_per_unit
            factor = _conversion_factor(ing.unit, rp.unit)
            total += ing.quantity * factor * unit_cost
        return total

    @property
    def total_cost_per_portion(self):
        return self.cost_per_portion() + (self.base_labor_per_portion or Decimal('0'))

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name = "Cubierta"
        verbose_name_plural = "Cubiertas"


class BaseBreadIngredient(models.Model):
    base_bread = models.ForeignKey(BaseBread, on_delete=models.CASCADE, related_name='ingredients', verbose_name="Base de pastel")
    raw_product = models.ForeignKey('RawProduct', on_delete=models.CASCADE, related_name='base_bread_uses', verbose_name="Materia prima")
    quantity = models.DecimalField(max_digits=10, decimal_places=3, help_text="Cantidad necesaria por porción (1 persona)", verbose_name="Cantidad")
    notes = models.CharField(max_length=200, blank=True, help_text="Nota opcional, ej. 'tamizado', 'derretido'", verbose_name="Notas")

    def __str__(self):
        return f"{self.quantity} {self.raw_product.get_unit_display()} de {self.raw_product.name}"

    @property
    def unit(self):
        return self.raw_product.unit

    @property
    def cost(self):
        rp = self.raw_product
        unit_cost = rp.average_cost if rp.average_cost else rp.cost_per_unit
        return self.quantity * _conversion_factor(self.unit, rp.unit) * unit_cost

    class Meta:
        unique_together = ('base_bread', 'raw_product')
        verbose_name = "Ingrediente de Base"
        verbose_name_plural = "Ingredientes de Base"


class FillingIngredient(models.Model):
    filling = models.ForeignKey(Filling, on_delete=models.CASCADE, related_name='ingredients', verbose_name="Relleno")
    raw_product = models.ForeignKey('RawProduct', on_delete=models.CASCADE, related_name='filling_uses', verbose_name="Materia prima")
    quantity = models.DecimalField(max_digits=10, decimal_places=3, help_text="Cantidad necesaria por porción (1 persona)", verbose_name="Cantidad")
    notes = models.CharField(max_length=200, blank=True, help_text="Nota opcional, ej. 'tamizado', 'derretido'", verbose_name="Notas")

    def __str__(self):
        return f"{self.quantity} {self.raw_product.get_unit_display()} de {self.raw_product.name}"

    @property
    def unit(self):
        return self.raw_product.unit

    @property
    def cost(self):
        rp = self.raw_product
        unit_cost = rp.average_cost if rp.average_cost else rp.cost_per_unit
        return self.quantity * _conversion_factor(self.unit, rp.unit) * unit_cost

    class Meta:
        unique_together = ('filling', 'raw_product')
        verbose_name = "Ingrediente de Relleno"
        verbose_name_plural = "Ingredientes de Relleno"


class ToppingIngredient(models.Model):
    topping = models.ForeignKey(Topping, on_delete=models.CASCADE, related_name='ingredients', verbose_name="Cubierta")
    raw_product = models.ForeignKey('RawProduct', on_delete=models.CASCADE, related_name='topping_uses', verbose_name="Materia prima")
    quantity = models.DecimalField(max_digits=10, decimal_places=3, help_text="Cantidad necesaria por porción (1 persona)", verbose_name="Cantidad")
    notes = models.CharField(max_length=200, blank=True, help_text="Nota opcional, ej. 'tamizado', 'derretido'", verbose_name="Notas")

    def __str__(self):
        return f"{self.quantity} {self.raw_product.get_unit_display()} de {self.raw_product.name}"

    @property
    def unit(self):
        return self.raw_product.unit

    @property
    def cost(self):
        rp = self.raw_product
        unit_cost = rp.average_cost if rp.average_cost else rp.cost_per_unit
        return self.quantity * _conversion_factor(self.unit, rp.unit) * unit_cost

    class Meta:
        unique_together = ('topping', 'raw_product')
        verbose_name = "Ingrediente de Cubierta"
        verbose_name_plural = "Ingredientes de Cubierta"


class Brand(models.Model):
    name = models.CharField(max_length=200, verbose_name="Nombre")
    description = models.TextField(blank=True, verbose_name="Descripción")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado")

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name = "Marca"
        verbose_name_plural = "Marcas"


class EventTag(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Nombre")

    class Meta:
        ordering = ['name']
        verbose_name = "Etiqueta de Evento"
        verbose_name_plural = "Etiquetas de Evento"

    def __str__(self):
        return self.name


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
    base_bread = models.ForeignKey(BaseBread, on_delete=models.PROTECT, null=True, blank=True, verbose_name="Base de pastel")
    filling = models.ForeignKey(Filling, on_delete=models.PROTECT, null=True, blank=True, verbose_name="Relleno")
    topping = models.ForeignKey(Topping, on_delete=models.PROTECT, null=True, blank=True, verbose_name="Cubierta")
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Marca")
    complexity_tier = models.ForeignKey(ComplexityTier, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Nivel de complejidad")
    base_labor_per_portion = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Mano de obra + overhead por porción (1 persona)", verbose_name="Mano de obra por porción")
    min_persons = models.PositiveIntegerField(default=1, verbose_name="Personas mínimas")
    max_persons = models.PositiveIntegerField(default=100, verbose_name="Personas máximas")
    event_tags = models.ManyToManyField('EventTag', blank=True, verbose_name="Etiquetas de evento")
    design_description = models.TextField(blank=True, verbose_name="Descripción de diseño")
    color_scheme = models.CharField(max_length=200, blank=True, verbose_name="Esquema de colores")
    gender = models.CharField(max_length=20, blank=True, choices=[('nino', 'Niño'), ('nina', 'Niña'), ('hombre', 'Hombre'), ('mujer', 'Mujer'), ('unisex', 'Unisex')], verbose_name="Género")
    show_in_gallery = models.BooleanField(default=False, verbose_name="Mostrar en galería")
    featured = models.BooleanField(default=False, verbose_name="Destacado en galería")

    def calculate_cost(self):
        """Return ingredient cost for ONE portion (1 person)."""
        if self.category == 'cake' and self.base_bread_id:
            base_cost = self.base_bread.cost_per_portion() if self.base_bread else Decimal('0')
            filling_cost = self.filling.cost_per_portion() if self.filling else Decimal('0')
            topping_cost = self.topping.cost_per_portion() if self.topping else Decimal('0')
            return base_cost + filling_cost + topping_cost
        total = Decimal('0')
        for ing in self.ingredients.select_related('raw_product'):
            rp = ing.raw_product
            unit_cost = rp.average_cost if rp.average_cost else rp.cost_per_unit
            factor = _conversion_factor(ing.unit, rp.unit)
            total += ing.quantity * factor * unit_cost
        return total

    def calculate_price_for(self, persons):
        """Calculate total price for N persons including ingredients, labor, and design surcharge."""
        persons = Decimal(str(persons))
        if self.category == 'cake' and self.base_bread_id:
            base_cost = self.base_bread.cost_per_portion() if self.base_bread else Decimal('0')
            filling_cost = self.filling.cost_per_portion() if self.filling else Decimal('0')
            topping_cost = self.topping.cost_per_portion() if self.topping else Decimal('0')
            ingredient_cost = (base_cost + filling_cost + topping_cost) * persons

            base_labor = self.base_bread.base_labor_per_portion if self.base_bread else Decimal('0')
            filling_labor = self.filling.base_labor_per_portion if self.filling else Decimal('0')
            topping_labor = self.topping.base_labor_per_portion if self.topping else Decimal('0')
            labor_cost = (base_labor + filling_labor + topping_labor) * persons
        else:
            ingredient_cost = self.calculate_cost() * persons
            labor_cost = (self.base_labor_per_portion or Decimal('0')) * persons
        base_total = ingredient_cost + labor_cost
        if self.complexity_tier:
            surcharge = base_total * (self.complexity_tier.surcharge_percentage / Decimal('100'))
        else:
            surcharge = Decimal('0')
        return {
            'persons': persons,
            'ingredient_cost': ingredient_cost,
            'labor_cost': labor_cost,
            'base_total': base_total,
            'design_surcharge': surcharge,
            'total': base_total + surcharge,
            'price_per_person': (base_total + surcharge) / persons if persons > 0 else Decimal('0'),
        }

    def calculate_margin(self):
        if self.cost > 0:
            return ((self.price - self.cost) / self.cost) * 100
        return 0

    def check_stock_for(self, persons):
        """Returns shortage list for producing enough for N persons."""
        shortages = []
        for ing in self.ingredients.select_related('raw_product'):
            rp = ing.raw_product
            needed = ing.quantity * _conversion_factor(ing.unit, rp.unit) * Decimal(str(persons))
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
        return f"{self.name} ({self.quantity_in_stock} en stock)"

    class Meta:
        ordering = ['name']
        verbose_name = "Producto"
        verbose_name_plural = "Productos"


class Client(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Usuario",
        null=True, blank=True,
    )
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
        ('pending',       'Pendiente'),
        ('approved',      'Aprobado'),
        ('in_production', 'En producción'),
        ('delivered',     'Entregado'),
        ('paid',          'Pagado'),
        ('cancelled',     'Cancelado'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='orders', verbose_name="Cliente")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='orders', verbose_name="Producto")
    persons = models.PositiveIntegerField(default=1, verbose_name="Personas")
    unit_price = models.DecimalField(max_digits=16, decimal_places=6, default=0, help_text="Precio por persona", verbose_name="Precio por persona")
    design_notes = models.TextField(blank=True, verbose_name="Notas de diseño")
    design_surcharge = models.DecimalField(max_digits=16, decimal_places=6, default=0, verbose_name="Recargo por diseño")
    labor_cost = models.DecimalField(max_digits=16, decimal_places=6, default=0, verbose_name="Mano de obra")
    total_price = models.DecimalField(max_digits=16, decimal_places=6, verbose_name="Precio total")
    delivery_cost = models.DecimalField(max_digits=16, decimal_places=6, default=0, verbose_name="Costo de envío")
    order_date = models.DateTimeField(auto_now_add=True, verbose_name="Fecha del pedido")
    deadline = models.DateField(null=True, blank=True, verbose_name="Fecha de entrega")
    stock_verified = models.BooleanField(default=False, verbose_name="Stock verificado")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Estado")
    notes = models.TextField(blank=True, null=True, verbose_name="Notas")

    def save(self, *args, **kwargs):
        if self.product:
            breakdown = self.product.calculate_price_for(self.persons or 1)
            self.unit_price = breakdown['price_per_person']
            self.design_surcharge = breakdown['design_surcharge']
            self.labor_cost = breakdown['labor_cost']
            self.total_price = breakdown['total']
        super().save(*args, **kwargs)

    @property
    def grand_total(self):
        return (self.total_price or 0) + (self.delivery_cost or 0)

    def check_stock_shortages(self):
        """Returns list of missing ingredients for this order's product × persons."""
        return self.product.check_stock_for(self.persons) if self.product else []

    def __str__(self):
        return f"Pedido #{self.id} – {self.client.name} ({self.product.name} × {self.persons} pers.)"

    class Meta:
        ordering = ['-order_date']
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"


class Provider(models.Model):
    name = models.CharField(max_length=200, verbose_name="Nombre")
    contact_person = models.CharField(max_length=200, blank=True, verbose_name="Persona de contacto")
    email = models.EmailField(verbose_name="Email")
    phone = models.CharField(max_length=20, verbose_name="Teléfono")
    address = models.TextField(blank=True, verbose_name="Dirección")
    city = models.CharField(max_length=100, blank=True, verbose_name="Ciudad")
    postal_code = models.CharField(max_length=20, blank=True, verbose_name="Código postal")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado")

    def __str__(self):
        return f"{self.name} ({self.contact_person})"

    class Meta:
        ordering = ['name']
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"


class RawProduct(models.Model):
    UNIT_CHOICES = [
        ('kg', 'Kilogramo'),
        ('g', 'Gramo'),
        ('l', 'Litro'),
        ('ml', 'Mililitro'),
        ('unit', 'Unidad'),
        ('box', 'Caja'),
        ('dozen', 'Docena'),
    ]

    name = models.CharField(max_length=200, verbose_name="Nombre")
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Marca")
    description = models.TextField(blank=True, verbose_name="Descripción")
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='kg', verbose_name="Unidad")
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=6, verbose_name="Último costo", help_text="Costo de la compra más reciente", default=0)
    average_cost = models.DecimalField(max_digits=10, decimal_places=6, default=0, help_text="Costo promedio ponderado entre todas las compras", verbose_name="Costo promedio")
    quantity_in_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Cantidad en stock")
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=10, verbose_name="Nivel de reorden")
    provider = models.ForeignKey(Provider, on_delete=models.SET_NULL, null=True, blank=True, related_name='raw_products', verbose_name="Proveedor")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado")

    def __str__(self):
        brand_str = f" [{self.brand.name}]" if self.brand else ""
        return f"{self.name}{brand_str} ({self.quantity_in_stock} {self.unit})"

    class Meta:
        ordering = ['name', 'brand__name']
        verbose_name = "Materia Prima"
        verbose_name_plural = "Materias Primas"


class ProviderCatalog(models.Model):
    raw_product  = models.ForeignKey(RawProduct, on_delete=models.CASCADE, related_name='provider_prices', verbose_name="Materia prima")
    provider     = models.ForeignKey(Provider,   on_delete=models.CASCADE, related_name='catalog_prices', verbose_name="Proveedor")
    unit_price   = models.DecimalField(max_digits=16, decimal_places=6, help_text="Precio por unidad ofrecido por este proveedor", verbose_name="Precio unitario")
    notes        = models.CharField(max_length=300, blank=True, verbose_name="Notas")
    updated_at   = models.DateTimeField(auto_now=True, verbose_name="Actualizado")

    class Meta:
        unique_together = ('raw_product', 'provider')
        ordering = ['unit_price']
        verbose_name = "Precio de Proveedor"
        verbose_name_plural = "Precios de Proveedores"

    def __str__(self):
        return f"{self.provider.name} → {self.raw_product.name}: ${self.unit_price}"


class Purchase(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('received', 'Recibida'),
        ('cancelled', 'Cancelada'),
    ]

    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, related_name='purchases', verbose_name="Proveedor")
    purchase_date = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de compra")
    delivery_date = models.DateField(blank=True, null=True, verbose_name="Fecha de entrega")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Estado")
    notes = models.TextField(blank=True, verbose_name="Notas")

    @property
    def total_cost(self):
        return sum(item.item_total for item in self.items.all())

    def __str__(self):
        return f"Compra #{self.id} – {self.provider.name} ({self.get_status_display()})"

    class Meta:
        ordering = ['-purchase_date']
        verbose_name = "Compra"
        verbose_name_plural = "Compras"


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='items', verbose_name="Compra")
    raw_product = models.ForeignKey(RawProduct, on_delete=models.PROTECT, related_name='purchase_items', verbose_name="Materia prima")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Cantidad")
    unit_cost = models.DecimalField(max_digits=16, decimal_places=6, help_text="Costo por unidad", verbose_name="Costo unitario")
    item_total = models.DecimalField(max_digits=16, decimal_places=6, editable=False, default=0, verbose_name="Total")

    def save(self, *args, **kwargs):
        self.item_total = self.quantity * self.unit_cost
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.raw_product.name} x{self.quantity}"

    class Meta:
        verbose_name = "Artículo de Compra"
        verbose_name_plural = "Artículos de Compra"


class RecipeIngredient(models.Model):
    UNIT_CHOICES = [
        ('g', 'Gramos'),
        ('mg', 'Miligramos'),
        ('pcs', 'Piezas'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='ingredients', verbose_name="Producto")
    raw_product = models.ForeignKey(RawProduct, on_delete=models.CASCADE, related_name='recipe_uses', verbose_name="Materia prima")
    quantity = models.DecimalField(max_digits=10, decimal_places=3, help_text="Cantidad necesaria", verbose_name="Cantidad")
    unit = models.CharField(max_length=5, choices=UNIT_CHOICES, default='g', verbose_name="Unidad")
    notes = models.CharField(max_length=200, blank=True, help_text="Nota opcional, ej. 'tamizado', 'derretido'", verbose_name="Notas")

    def __str__(self):
        return f"{self.quantity} {self.get_unit_display()} de {self.raw_product.name}"

    class Meta:
        unique_together = ('product', 'raw_product')
        verbose_name = "Ingrediente"
        verbose_name_plural = "Ingredientes"


class Quote(models.Model):
    STATUS_CHOICES = [
        ('draft',    'Borrador'),
        ('sent',     'Enviada'),
        ('accepted', 'Aceptada'),
        ('rejected', 'Rechazada'),
        ('expired',  'Expirada'),
    ]

    client        = models.ForeignKey(Client,  on_delete=models.CASCADE, related_name='quotes', verbose_name="Cliente")
    product       = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='quotes', verbose_name="Producto (opcional)")
    name          = models.CharField(max_length=200, blank=True, default='', verbose_name="Nombre del pastel")
    base_bread    = models.ForeignKey(BaseBread, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Base de pastel")
    filling       = models.ForeignKey(Filling,   on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Relleno")
    topping       = models.ForeignKey(Topping,   on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Cubierta")
    complexity_tier = models.ForeignKey(ComplexityTier, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Nivel de complejidad")
    benefit_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=50, help_text="Porcentaje de beneficio aplicado sobre el costo", verbose_name="% Beneficio")
    persons       = models.PositiveIntegerField(default=1, verbose_name="Personas")
    unit_price    = models.DecimalField(max_digits=16, decimal_places=6, default=0, help_text="Precio por persona (incluye beneficio y diseño)", verbose_name="Precio por persona")
    ingredient_cost = models.DecimalField(max_digits=16, decimal_places=6, default=0, verbose_name="Ingredientes")
    design_notes  = models.TextField(blank=True, verbose_name="Notas de diseño")
    design_surcharge = models.DecimalField(max_digits=16, decimal_places=6, default=0, verbose_name="Recargo por diseño")
    labor_cost    = models.DecimalField(max_digits=16, decimal_places=6, default=0, verbose_name="Mano de obra")
    benefit_amount = models.DecimalField(max_digits=16, decimal_places=6, default=0, verbose_name="Beneficio")
    delivery_cost = models.DecimalField(max_digits=16, decimal_places=6, default=0, verbose_name="Costo de envío")
    extras_amount = models.DecimalField(max_digits=16, decimal_places=6, default=0, verbose_name="Agregados")
    due_date      = models.DateField(verbose_name="Fecha de vencimiento")
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="Estado")
    notes         = models.TextField(blank=True, verbose_name="Notas")
    created_at    = models.DateTimeField(auto_now_add=True, verbose_name="Creado")
    updated_at    = models.DateTimeField(auto_now=True, verbose_name="Actualizado")

    @property
    def cake_name(self):
        if self.name:
            return self.name
        if self.product:
            return self.product.name
        parts = [c.name for c in (self.base_bread, self.filling, self.topping) if c]
        return ' · '.join(parts) or 'Pastel'

    @property
    def total_price(self):
        """Subtotal = precio por persona × personas + agregados (incluye beneficio y diseño)."""
        return (self.unit_price or Decimal('0')) * (self.persons or 1) + (self.extras_amount or Decimal('0'))

    @property
    def components_total(self):
        """Subtotal sin agregados = precio por persona × personas."""
        return (self.unit_price or Decimal('0')) * (self.persons or 1)

    @property
    def total_cost(self):
        """Costo real (sin beneficio) = ingredientes + mano de obra + diseño."""
        return (self.ingredient_cost or Decimal('0')) + (self.labor_cost or Decimal('0')) + (self.design_surcharge or Decimal('0'))

    @property
    def grand_total(self):
        return self.total_price + (self.delivery_cost or Decimal('0'))

    @property
    def days_until_due(self):
        from django.utils import timezone
        return (self.due_date - timezone.now().date()).days

    def recalculate(self):
        self.extras_amount = sum((ag.amount or Decimal('0')) for ag in self.agregados.all())
        has_components = self.base_bread_id or self.filling_id or self.topping_id
        if has_components:
            b = calculate_components_cost(
                self.base_bread, self.filling, self.topping,
                self.complexity_tier, self.persons or 1, self.benefit_percentage,
                self.extras_amount,
            )
            self.ingredient_cost = b['ingredient_cost']
            self.labor_cost = b['labor_cost']
            self.design_surcharge = b['design_surcharge']
            self.benefit_amount = b['benefit_amount']
            self.unit_price = b['unit_price']
        elif self.product:
            b = self.product.calculate_price_for(self.persons or 1)
            benefit = (self.benefit_percentage or Decimal('0')) / Decimal('100')
            self.ingredient_cost = b['ingredient_cost']
            self.labor_cost = b['labor_cost']
            self.design_surcharge = b['design_surcharge']
            self.benefit_amount = (b['base_total'] + b['design_surcharge'] + self.extras_amount) * benefit
            self.unit_price = b['price_per_person'] * (Decimal('1') + benefit)
    def ensure_product(self):
        """Crea/recupera el Producto únicamente al momento de la venta."""
        if self.product_id:
            return self.product
        product, _ = Product.objects.get_or_create(
            name=self.cake_name,
            category='cake',
            base_bread=self.base_bread,
            filling=self.filling,
            topping=self.topping,
            defaults={
                'complexity_tier': self.complexity_tier,
                'is_available': True,
                'price': Decimal('0'),
            },
        )
        self.product = product
        self.save(update_fields=['product'])
        return product

    def __str__(self):
        return f"Cotización #{self.id} – {self.client.name} ({self.cake_name} × {self.persons} pers.)"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Cotización"
        verbose_name_plural = "Cotizaciones"


class QuoteAgregado(models.Model):
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name='agregados', verbose_name="Cotización")
    description = models.CharField(max_length=200, verbose_name="Descripción")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Monto")

    def __str__(self):
        return f"{self.description} (${self.amount})"

    class Meta:
        ordering = ['id']
        verbose_name = "Agregado de Cotización"
        verbose_name_plural = "Agregados de Cotización"
