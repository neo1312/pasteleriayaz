document.addEventListener('DOMContentLoaded', function() {
    var productSelect = document.getElementById('id_product');
    var priceInput = document.getElementById('id_unit_price');

    if (!productSelect || !priceInput) return;

    var baseUrl = window.location.pathname.split('/').slice(0, -3).join('/');

    productSelect.addEventListener('change', function() {
        var productId = this.value;
        if (!productId) {
            if (!priceInput.value || priceInput.value === '0') {
                priceInput.value = '';
            }
            return;
        }

        fetch(baseUrl + '/product-price/' + productId + '/')
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (data.price) {
                    priceInput.value = data.price;
                }
            })
            .catch(function() {});
    });
});
