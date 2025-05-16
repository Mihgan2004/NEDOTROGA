/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { Many2oneField, many2OneField } from "@web/views/fields/many2one/many2one_field"; // База для Many2one

const { Component, useState, onWillStart, onWillUpdateProps, onMounted, onWillUnmount, useRef } = owl;

export class CdekPvzSelectorAndMap extends Component {
    static template = "cdek_integration.CdekPvzSelectorAndMap";
    static props = {
        ...many2OneField.props, // Наследуем props от стандартного Many2oneField
        // Дополнительные props, если нужны из XML (options)
        yandexMapsApiKey: { type: String, optional: true }, // API ключ можно передать через options
    };

    setup() {
        this.orm = useService("orm");
        this.rpc = useService("rpc");
        this.notificationService = useService("notification"); // Переименовал для ясности

        this.state = useState({
            // Для текстового селекта
            currentSearchInput: "",
            searchResults: [], // [{id, code, name, address_full, city_name, latitude, longitude}, ...]
            showDropdown: false,
            activeIndex: -1,
            
            // Для карты
            mapInitialized: false,
            pvzForMap: [], // ПВЗ, которые сейчас отображаются на карте
            mapIsLoading: false,
            mapError: null,
            
            // Общее
            selectedPvzDisplayInfo: "", // Для отображения над картой или инпутом
            isLoadingPvzDetails: false, // Если грузим детали для уже выбранного ID
            
            // Контекст
            defaultCityName: "",
            defaultCountryCode: "RU", // По умолчанию Россия
        });

        this.inputRef = useRef("pvzSearchInput");
        this.dropdownRef = useRef("pvzDropdown");
        this.mapContainerRef = useRef("mapContainer");
        this.yandexMap = null; // Экземпляр Яндекс.Карты
        this.mapPlacemarks = []; // Коллекция маркеров на карте

        this.debouncedSearchPvzs = useDebounced(this._performPvzSearch, 400);
        this.debouncedGeocodeCityAndLoadMap = useDebounced(this._geocodeCityAndLoadMap, 500);

        this._getContextValues(this.props);

        onWillStart(async () => {
            // Если поле уже имеет значение, загружаем информацию о нем
            if (this.props.value && this.props.value[0]) {
                await this._loadAndDisplayPvzById(this.props.value[0]);
            }
            // Инициализация города для карты, если он есть
            if (this.state.defaultCityName) {
                 this.debouncedGeocodeCityAndLoadMap(this.state.defaultCityName, this.state.defaultCountryCode);
            }
        });
        
        onMounted(async () => {
            document.addEventListener("click", this._onClickOutsideWidget, true);
            // Загрузка API Яндекс.Карт
            try {
                await this._loadYandexMapsApi();
                this._initMapBase(); // Базовая инициализация карты
            } catch (e) {
                this.state.mapError = this.env._t("Failed to load Yandex Maps API.");
                console.error(e);
            }
        });

        onWillUpdateProps(async (nextProps) => {
            this._getContextValues(nextProps);
            // Если значение поля изменилось извне
            if (nextProps.value !== this.props.value) {
                if (nextProps.value && nextProps.value[0]) {
                    await this._loadAndDisplayPvzById(nextProps.value[0]);
                } else {
                    this.state.currentSearchInput = "";
                    this.state.selectedPvzDisplayInfo = "";
                    this.state.searchResults = [];
                    this.state.showDropdown = false;
                    this.clearMapPlacemarks(); // Очистить карту, если выбор сброшен
                }
            }
            // Если изменился город доставки
            if (nextProps.record.data.partner_shipping_id_city !== this.props.record.data.partner_shipping_id_city ||
                nextProps.record.data.partner_shipping_id_country_code !== this.props.record.data.partner_shipping_id_country_code) {
                if (this.state.defaultCityName) { // defaultCityName уже обновлен через _getContextValues
                    this.debouncedGeocodeCityAndLoadMap(this.state.defaultCityName, this.state.defaultCountryCode);
                } else {
                    this.clearMapPlacemarks(); // Если город стерли, очищаем карту
                    this.state.pvzForMap = [];
                }
            }
        });

        onWillUnmount(() => {
            document.removeEventListener("click", this._onClickOutsideWidget, true);
            if (this.yandexMap) {
                this.yandexMap.destroy();
                this.yandexMap = null;
            }
        });
    }

    _getContextValues(props) {
        this.state.defaultCityName = props.record.data.partner_shipping_id_city || "";
        this.state.defaultCountryCode = props.record.data.partner_shipping_id_country_code || "RU";
    }

    async _loadAndDisplayPvzById(pvzId) {
        this.state.isLoadingPvzDetails = true;
        try {
            const pvzData = await this.orm.read("cdek.pvz", [pvzId], ["id", "code", "name", "address_full", "city_name", "latitude", "longitude"]);
            if (pvzData && pvzData.length > 0) {
                const pvz = pvzData[0];
                this.state.selectedPvzDisplayInfo = `${pvz.code} - ${pvz.name} (${pvz.address_full})`;
                this.state.currentSearchInput = this.state.selectedPvzDisplayInfo; // Заполняем инпут
                // Обновляем карту, если она инициализирована
                this.state.pvzForMap = [pvz]; // Для карты нужен массив
                if (this.yandexMap && pvz.latitude && pvz.longitude) {
                    this.clearMapPlacemarks();
                    this.addPvzToMap(pvz, true); // true - центрировать и выделить
                    this.yandexMap.setCenter([pvz.latitude, pvz.longitude], 15);
                } else if (pvz.city_name) { // Если карты нет, но есть город ПВЗ
                    this.debouncedGeocodeCityAndLoadMap(pvz.city_name, this.state.defaultCountryCode, [pvz]);
                }
            }
        } catch (error) {
            console.error("Error loading selected PVZ details:", error);
            this.notificationService.add(this.env._t("Error loading PVZ details."), { type: "danger" });
        } finally {
            this.state.isLoadingPvzDetails = false;
        }
    }
    
    // --- Логика текстового селекта ---
    onSearchInput(ev) {
        this.state.currentSearchInput = ev.target.value;
        if (this.state.currentSearchInput.length === 0) {
            this.state.searchResults = [];
            this.state.showDropdown = false;
            // Можно также очистить this.props.update(false) если нужно очищать выбор при пустом инпуте
        } else if (this.state.currentSearchInput.length >= 2) {
            this.state.showDropdown = true; // Показать дропдаун сразу при вводе
            this.debouncedSearchPvzs();
        } else {
            this.state.searchResults = [];
            this.state.showDropdown = false;
        }
    }

    async _performPvzSearch() {
        if (this.state.currentSearchInput.length < 2 && !this.state.defaultCityName) {
            this.state.searchResults = []; this.state.showDropdown = false; return;
        }
        this.state.isLoadingPvzDetails = true; // Используем общий флаг загрузки
        try {
            // Используем контроллер /cdek/pvz/search
            const results = await this.rpc("/cdek/pvz/search", {
                city_name: this.state.defaultCityName, // Город из контекста (адреса доставки)
                country_code: this.state.defaultCountryCode,
                search_text: this.state.currentSearchInput, // Текст из поля ввода для фильтрации ПВЗ
                limit: 10 // Задача: до 10 результатов в списке
            });
            this.state.searchResults = results;
            this.state.showDropdown = results.length > 0;
            
            // Обновляем маркеры на карте на основе результатов поиска (текстового)
            this.state.pvzForMap = results; // Обновляем данные для карты
            if (this.yandexMap) {
                this.updateMapWithPvzList(results);
            }

        } catch (error) {
            console.error("Error searching PVZ:", error);
            this.notificationService.add(this.env._t("Error searching PVZ."), { type: "danger" });
            this.state.searchResults = []; this.state.showDropdown = false;
        } finally {
            this.state.isLoadingPvzDetails = false;
        }
    }
    
    async selectPvz(pvz) {
        this.state.showDropdown = false;
        this.state.selectedPvzDisplayInfo = `${pvz.code} - ${pvz.name} (${pvz.address_full})`;
        this.state.currentSearchInput = this.state.selectedPvzDisplayInfo; // Обновляем инпут
        
        // Обновляем поле Many2one (cdek_pvz_id)
        await this.props.update([{ id: pvz.id, display_name: `${pvz.code} - ${pvz.name}` }]);
        
        // Смежные поля (cdek_pvz_code, cdek_pvz_name, cdek_pvz_address_full)
        // обновятся автоматически, если они `related` с `store=True`.
        // Если нет, то нужно this.props.record.update(...) - но это мы убрали в пользу related

        // Выделить и центрировать на карте
        if (this.yandexMap && pvz.latitude && pvz.longitude) {
            this.highlightMapPlacemark(pvz.code, true); // true для открытия балуна
            this.yandexMap.setCenter([pvz.latitude, pvz.longitude], 15);
        }
        if (this.inputRef.el) this.inputRef.el.blur(); // Убрать фокус с инпута
    }

    onInputKeyDown(ev) {
        if (!this.state.showDropdown || this.state.searchResults.length === 0) return;
        switch (ev.key) {
            case "ArrowDown":
                ev.preventDefault();
                this.state.activeIndex = (this.state.activeIndex + 1) % this.state.searchResults.length;
                this._scrollToActiveInDropdown();
                break;
            case "ArrowUp":
                ev.preventDefault();
                this.state.activeIndex = (this.state.activeIndex - 1 + this.state.searchResults.length) % this.state.searchResults.length;
                this._scrollToActiveInDropdown();
                break;
            case "Enter":
                ev.preventDefault();
                if (this.state.activeIndex >= 0 && this.state.activeIndex < this.state.searchResults.length) {
                    this.selectPvz(this.state.searchResults[this.state.activeIndex]);
                }
                break;
            case "Escape":
                this.state.showDropdown = false; this.state.activeIndex = -1;
                break;
            case "Tab":
                this.state.showDropdown = false; this.state.activeIndex = -1;
                break;
        }
    }
    
    _scrollToActiveInDropdown() {
        if (this.dropdownRef.el && this.state.activeIndex >= 0) {
            const activeItem = this.dropdownRef.el.querySelector(`.pvz-dropdown-item[data-index="${this.state.activeIndex}"]`);
            if (activeItem) activeItem.scrollIntoView({ block: 'nearest' });
        }
    }

    async clearPvzSelection(ev) {
        if(ev) ev.stopPropagation();
        this.state.currentSearchInput = "";
        this.state.selectedPvzDisplayInfo = "";
        this.state.searchResults = [];
        this.state.showDropdown = false;
        await this.props.update(false); // Очищаем поле cdek_pvz_id
        // Связанные поля очистятся автоматически
        this.clearMapPlacemarks(); // Очищаем карту
        if (this.inputRef.el) this.inputRef.el.focus();
    }

    _onClickOutsideWidget(ev) {
        if (this.el && !this.el.contains(ev.target)) {
            this.state.showDropdown = false;
            this.state.activeIndex = -1;
        }
    }

    // --- Логика Карты ---
    async _loadYandexMapsApi() {
        return new Promise((resolve, reject) => {
            if (window.ymaps && window.ymaps.Map) { // Проверяем наличие ymaps.Map
                resolve();
                return;
            }
            const apiKey = this.props.yandexMapsApiKey || this.env.session?.user_context?.cdek_yandex_maps_api_key || ""; // Ключ из пропсов или user_context
            const script = document.createElement('script');
            script.src = `https://api-maps.yandex.ru/2.1/?lang=ru_RU&apikey=${apiKey}`;
            script.async = true;
            script.onload = () => {
                console.log("Yandex Maps API script loaded.");
                if (window.ymaps) {
                     ymaps.ready(resolve);
                } else {
                    console.error("Yandex Maps API loaded but ymaps object not found.");
                    reject("ymaps object not found after script load.");
                }
            };
            script.onerror = (err) => {
                console.error("Failed to load Yandex Maps API script:", err);
                this.state.mapError = this.env._t("Failed to load Yandex Maps API script.");
                reject(err);
            };
            document.head.appendChild(script);
        });
    }

    _initMapBase() {
        if (!this.mapContainerRef.el || !window.ymaps || this.yandexMap) return;
        try {
            this.yandexMap = new ymaps.Map(this.mapContainerRef.el, {
                center: [55.751574, 37.573856], // Москва по умолчанию
                zoom: 9,
                controls: ['zoomControl', 'fullscreenControl', 'searchControl'] // Добавил searchControl
            });
            this.state.mapInitialized = true;
            console.log("Yandex Map base initialized.");
        } catch(e) {
            console.error("Error initializing Yandex Map:", e);
            this.state.mapError = this.env._t("Error initializing map: ") + e.message;
        }
    }
    
    async _geocodeCityAndLoadMap(cityName, countryCode = 'RU', initialPvzs = null) {
        if (!cityName) {
            this.updateMapWithPvzList(initialPvzs || []); // Показать начальные ПВЗ если город пуст
            return;
        }
        if (!this.yandexMap && this.state.mapInitialized === false) { // Если карта еще не инициализирована базово
            await this._loadYandexMapsApi(); // Убедимся что API загружено
            this._initMapBase();             // Инициализируем карту
        }
        if (!this.yandexMap) {
             _logger.warn("Map not ready for geocoding city " + cityName);
             return; // Карта все еще не готова
        }

        this.state.mapIsLoading = true;
        this.state.mapError = null;

        try {
            // 1. Геокодируем город через API Яндекс.Карт (для центрирования)
            const geocodeResult = await ymaps.geocode(`${countryCode}, ${cityName}`, { results: 1 });
            const firstGeoObject = geocodeResult.geoObjects.get(0);
            if (firstGeoObject) {
                this.yandexMap.setCenter(firstGeoObject.geometry.getCoordinates(), 10); // Зум 10 для города
            } else {
                 _logger.warn(`Could not geocode city: ${cityName}`);
            }

            // 2. Запрашиваем ПВЗ для этого города через наш контроллер, если initialPvzs не переданы
            if (!initialPvzs) {
                const pvzData = await this.rpc("/cdek/pvz/search", {
                    city_name: cityName,
                    country_code: countryCode,
                    search_text: "", // Без доп. фильтрации по тексту, только по городу
                    limit: 200 // Больше лимит для карты
                });
                this.state.pvzForMap = pvzData;
                this.updateMapWithPvzList(pvzData);
            } else { // Если initialPvzs переданы (например, при выборе ПВЗ из списка)
                 this.state.pvzForMap = initialPvzs;
                 this.updateMapWithPvzList(initialPvzs);
            }

        } catch (error) {
            console.error(`Error geocoding city ${cityName} or fetching PVZs for map:`, error);
            this.state.mapError = this.env._t("Error loading PVZ data for map.");
            this.updateMapWithPvzList([]); // Очищаем карту при ошибке
        } finally {
            this.state.mapIsLoading = false;
        }
    }

    updateMapWithPvzList(pvzList) {
        if (!this.yandexMap) return;
        this.clearMapPlacemarks();
        if (pvzList && pvzList.length > 0) {
            pvzList.forEach(pvz => this.addPvzToMap(pvz));
            // Автоматическое масштабирование и центрирование карты по всем точкам
            if (this.mapPlacemarks.length > 0) {
                 this.yandexMap.setBounds(this.yandexMap.geoObjects.getBounds(), {
                     checkZoomRange: true,
                     zoomMargin: 30
                 });
            }
        } else {
             _logger.info("No PVZs to display on map for current criteria.");
        }
    }

    addPvzToMap(pvz, openBalloon = false) {
        if (!this.yandexMap || !pvz.latitude || !pvz.longitude) return;

        const placemark = new ymaps.Placemark([pvz.latitude, pvz.longitude], {
            hintContent: pvz.name,
            balloonContentHeader: pvz.name,
            balloonContentBody: `
                <div class="cdek-pvz-balloon">
                    <p><strong>Код:</strong> ${pvz.code}</p>
                    <p>${pvz.address_full || ''}</p>
                    <p><strong>Время работы:</strong> ${pvz.work_time || 'N/A'}</p>
                    ${pvz.phone ? `<p><strong>Телефон:</strong> ${pvz.phone}</p>` : ''}
                </div>`,
            // Можно передать ID ПВЗ для связи
            pvzId: pvz.id, 
            pvzCode: pvz.code
        }, {
            preset: 'islands#blueDotIcon', // Стандартный синий маркер
            // iconColor: pvz.is_cod ? '#FF0000' : '#0095B6' // Пример: красный для НП
        });

        placemark.events.add('click', async () => {
            // При клике на маркер - выбираем этот ПВЗ
            await this.selectPvz(pvz); // Используем существующий метод выбора
            // Балун откроется сам при клике, если не отключено
        });
        
        this.mapPlacemarks.push(placemark);
        this.yandexMap.geoObjects.add(placemark);

        if (openBalloon) {
            placemark.balloon.open();
        }
    }
    
    highlightMapPlacemark(pvzCode, openBalloon = false) {
        if (!this.yandexMap) return;
        this.mapPlacemarks.forEach(pm => {
            // Сначала можно сбросить стиль для всех (если есть кастомный стиль выделения)
            // pm.options.set('preset', 'islands#blueDotIcon'); 
            if (pm.properties.get('pvzCode') === pvzCode) {
                // pm.options.set('preset', 'islands#redDotIcon'); // Выделяем красным
                if (openBalloon && !pm.balloon.isOpen()) {
                    pm.balloon.open();
                }
                 this.yandexMap.panTo(pm.geometry.getCoordinates(), {flying: true});
            }
        });
    }

    clearMapPlacemarks() {
        if (this.yandexMap) {
            this.mapPlacemarks.forEach(pm => this.yandexMap.geoObjects.remove(pm));
        }
        this.mapPlacemarks = [];
    }
}

registry.category("fields").add("cdek_pvz_selector_map", CdekPvzSelectorAndMap);