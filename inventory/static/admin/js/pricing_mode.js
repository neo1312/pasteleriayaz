'use strict';
document.addEventListener('DOMContentLoaded', function () {
  var $ = django.jQuery;
  var $mode   = $('#id_pricing_mode');
  var $price  = $('#id_price');
  var $margin = $('#id_margin_percentage');

  if (!$mode.length) return;

  function rowOf($input) {
    // Django admin wraps each field in a <div class="form-row field-FIELDNAME">
    return $input.closest('[class*="field-"]');
  }

  function apply(mode) {
    if (mode === 'price') {
      // User sets price → margin is auto
      $price.prop('disabled', false).css({ background: '', color: '' });
      rowOf($price).find('.auto-label').remove();

      $margin.prop('disabled', true).css({ background: '#f0f0f0', color: '#999' });
      if (!rowOf($margin).find('.auto-label').length) {
        $margin.after(
          '<span class="auto-label" style="margin-left:8px;font-style:italic;color:#888;">' +
          '⟵ auto-calculated</span>'
        );
      }
    } else {
      // User sets margin → price is auto
      $margin.prop('disabled', false).css({ background: '', color: '' });
      rowOf($margin).find('.auto-label').remove();

      $price.prop('disabled', true).css({ background: '#f0f0f0', color: '#999' });
      if (!rowOf($price).find('.auto-label').length) {
        $price.after(
          '<span class="auto-label" style="margin-left:8px;font-style:italic;color:#888;">' +
          '⟵ auto-calculated</span>'
        );
      }
    }
  }

  // Apply current mode on page load
  apply($mode.val());

  // React to mode changes immediately
  $mode.on('change', function () { apply($(this).val()); });

  // Re-enable both fields before submit so values reach save_model
  // (save_model ignores the auto field anyway and recalculates it)
  $mode.closest('form').on('submit', function () {
    $price.prop('disabled', false);
    $margin.prop('disabled', false);
  });
});
