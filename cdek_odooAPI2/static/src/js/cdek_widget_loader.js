odoo.define('cdek_widget.loader', function(require) {
    'use strict';
    var publicWidget = require('web.public.widget');

    publicWidget.registry.CdekWidget = publicWidget.Widget.extend({
        selector: '#cdek_widget_container',

        start: function () {
            if (typeof ISDEKWidjet === 'function') {
                new ISDEKWidjet({
                    defaultCity: 'Москва',
                    cityFrom: 'Москва',
                    country: 'Россия',
                    link: 'forpvz',
                    onChoose: function (pvz) {
                        console.log('Выбран ПВЗ:', pvz);
                        // Здесь можно отправить данные на backend
                    }
                });
            } else {
                console.error('ISDEKWidjet не найден');
            }
            return this._super.apply(this, arguments);
        },
    });
});
