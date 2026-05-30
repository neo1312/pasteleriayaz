from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from decimal import Decimal

# Stores previous PurchaseItem values (qty, cost) before an update
_purchaseitem_prev = {}


# Track previous Purchase status to detect transitions
_purchase_prev_status = {}


@receiver(pre_save, sender='inventory.Purchase')
def track_purchase_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            from .models import Purchase
            _purchase_prev_status[instance.pk] = Purchase.objects.get(pk=instance.pk).status
        except Purchase.DoesNotExist:
            pass


@receiver(post_save, sender='inventory.Purchase')
def update_stock_on_purchase_received(sender, instance, created, **kwargs):
    prev = _purchase_prev_status.pop(instance.pk, None)
    if instance.status != 'received':
        return
    if prev == 'received':
        return  # already processed

    for item in instance.items.select_related('raw_product'):
        rp = item.raw_product
        old_stock = rp.quantity_in_stock or Decimal('0')
        old_avg = rp.average_cost or Decimal('0')
        new_qty = item.quantity
        new_cost = item.unit_cost

        # Weighted moving average
        total_qty = old_stock + new_qty
        if total_qty > 0:
            rp.average_cost = (old_stock * old_avg + new_qty * new_cost) / total_qty
        else:
            rp.average_cost = new_cost

        rp.cost_per_unit = new_cost          # last purchase cost
        rp.quantity_in_stock = total_qty
        rp.save(update_fields=['average_cost', 'cost_per_unit', 'quantity_in_stock'])


# ── PurchaseItem signals ──────────────────────────────────────────────────────
# These handle the case where items are added/edited on an already-received
# purchase (including the Django admin inline flow where the Purchase is saved
# first and items are saved afterwards).

@receiver(pre_save, sender='inventory.PurchaseItem')
def track_purchaseitem_prev(sender, instance, **kwargs):
    """Remember (quantity, unit_cost) before an update so we can reverse it."""
    if instance.pk:
        try:
            from .models import PurchaseItem
            old = PurchaseItem.objects.get(pk=instance.pk)
            _purchaseitem_prev[instance.pk] = (old.quantity, old.unit_cost)
        except PurchaseItem.DoesNotExist:
            pass


@receiver(post_save, sender='inventory.PurchaseItem')
def update_avg_cost_on_item_save(sender, instance, created, **kwargs):
    """Recalculate weighted average cost when an item is saved on a received purchase."""

    # Always keep ProviderCatalog up to date with the latest quoted price
    _update_provider_catalog(instance)

    if instance.purchase.status != 'received':
        return

    rp = instance.raw_product
    rp.refresh_from_db()  # make sure we have the latest values

    if created:
        # New item: apply incremental weighted average
        old_stock = rp.quantity_in_stock or Decimal('0')
        old_avg   = rp.average_cost or Decimal('0')
        new_qty   = instance.quantity
        new_cost  = instance.unit_cost

        total_qty = old_stock + new_qty
        rp.average_cost      = (old_stock * old_avg + new_qty * new_cost) / total_qty if total_qty else new_cost
        rp.cost_per_unit     = new_cost
        rp.quantity_in_stock = total_qty

    else:
        # Updated item: reverse old contribution, apply new one
        prev = _purchaseitem_prev.pop(instance.pk, None)
        if prev is None:
            return
        old_qty, old_cost = prev
        new_qty  = instance.quantity
        new_cost = instance.unit_cost

        if old_qty == new_qty and old_cost == new_cost:
            return  # nothing changed

        current_stock = rp.quantity_in_stock or Decimal('0')
        current_avg   = rp.average_cost or Decimal('0')

        # Undo old item's contribution to get the "pre-item" state
        prev_stock = current_stock - old_qty
        if prev_stock > 0:
            prev_value = current_stock * current_avg - old_qty * old_cost
            prev_avg   = prev_value / prev_stock
        else:
            prev_stock = Decimal('0')
            prev_avg   = Decimal('0')

        # Apply updated item
        total_qty = prev_stock + new_qty
        rp.average_cost      = (prev_stock * prev_avg + new_qty * new_cost) / total_qty if total_qty else new_cost
        rp.cost_per_unit     = new_cost
        rp.quantity_in_stock = total_qty

    rp.save(update_fields=['average_cost', 'cost_per_unit', 'quantity_in_stock'])

    # Auto-update ProviderCatalog with the latest purchase price
    _update_provider_catalog(instance)


def _update_provider_catalog(purchase_item):
    """Update or create a ProviderCatalog entry for this raw_product+provider pair."""
    from .models import ProviderCatalog
    provider = purchase_item.purchase.provider
    ProviderCatalog.objects.update_or_create(
        raw_product=purchase_item.raw_product,
        provider=provider,
        defaults={'unit_price': purchase_item.unit_cost},
    )
