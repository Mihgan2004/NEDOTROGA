/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField } from "@web/views/fields/char/char_field"; // Используем CharField как базу для стилизации input
import { useDebounced } from "@web/core/utils/timing";
import { useService } from "@web/core/utils/hooks";

const { Component, useState, onWillStart, onWillUpdateProps, useRef, onMounted } = owl;

export class CdekPvzSelector extends Component {
    static template = "your_module_name.CdekPvzSelector"; // Замените your_module_name
    static components = { CharField }; // Не обязательно, но может быть полезно для стилизации

    static props = {
        ...CharField.props, // Наследуем props от CharField или AbstractField
        // Odoo автоматически передаст 'record', 'name', 'update', 'value', и т.д.
        // value: [id, display_name] или false
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            defaultCityName: "",
            defaultCountryCode: "",
            currentInput: "", // Текст, который пользователь вводит для поиска
            searchResults: [], // Результаты поиска [{id, code, name, address_full}, ...]
            showDropdown: false,
            activeIndex: -1, // Для навигации по списку результатов
            selectedPvzDisplay: "", // Для отображения информации о выбранном ПВЗ
            isLoading: false,
        });

        this.inputRef = useRef("pvzInput");
        this.dropdownRef = useRef("pvzDropdown");

        // Получаем значения из контекста при инициализации
        this._getContextValues(this.props);

        // Debounce для функции поиска
        this.debouncedSearch = useDebounced(this._performSearch, 300);

        onWillStart(async () => {
            await this._updateSelectedPvzDisplay(this.props.record.data[this.props.name]);
        });

        onWillUpdateProps(async (nextProps) => {
            this._getContextValues(nextProps);
            await this._updateSelectedPvzDisplay(nextProps.record.data[this.props.name]);
            // Если значение было очищено извне (например, другим полем)
            if (!nextProps.record.data[this.props.name] && this.props.record.data[this.props.name]) {
                 this.state.currentInput = "";
            }
        });
        
        onMounted(() => {
            document.addEventListener("click", this._onClickOutside, true);
        });

        onWillUnmount(() => {
            document.removeEventListener("click", this._onClickOutside, true);
        });
    }

    _getContextValues(props) {
        const context = props.record.context || this.env.context || {};
        this.state.defaultCityName = context.default_city_name || "";
        this.state.defaultCountryCode = context.default_country_code || "";
    }

    async _updateSelectedPvzDisplay(pvzValue) {
        // pvzValue это [id, display_name] или false
        if (pvzValue && pvzValue[0]) {
            const pvzId = pvzValue[0];
            // Если нужные поля уже есть в display_name или мы их уже загрузили
            // (для примера, предположим что display_name не содержит всего, что нужно)
            // Можно сделать RPC для получения code и address_full, если они не в display_name
            // и не были ранее загружены и сохранены в cdek_pvz_code и cdek_pvz_address_full.
            // Проверяем, есть ли данные в связанных полях sale.order
            const recordData = this.props.record.data;
            if (recordData.cdek_pvz_code && recordData.cdek_pvz_name && recordData.cdek_pvz_address_full) {
                 this.state.selectedPvzDisplay = `${recordData.cdek_pvz_code} - ${recordData.cdek_pvz_name} (${recordData.cdek_pvz_address_full})`;
                 this.state.currentInput = this.state.selectedPvzDisplay; // Показываем текущее значение в input
            } else if (pvzId) {
                // Если поля не заполнены, но ID есть, попробуем загрузить
                this.state.isLoading = true;
                try {
                    const pvzData = await this.orm.read("cdek.pvz", [pvzId], ["id", "code", "name", "address_full"]);
                    if (pvzData && pvzData.length > 0) {
                        this.state.selectedPvzDisplay = `${pvzData[0].code} - ${pvzData[0].name} (${pvzData[0].address_full})`;
                        this.state.currentInput = this.state.selectedPvzDisplay;
                        // Обновляем поля в форме, если они пусты (например, при первой загрузке)
                        // Это немного спорно, так как виджет не должен напрямую менять то, что не его this.props.name
                        // Но по ТЗ нужно "заполнять соседние поля"
                         await this.props.record.update({
                            cdek_pvz_code: pvzData[0].code,
                            cdek_pvz_name: pvzData[0].name,
                            cdek_pvz_address_full: pvzData[0].address_full,
                        });
                    }
                } catch (error) {
                    console.error("Error fetching PVZ details:", error);
                    this.notification.add(this.env._t("Error fetching PVZ details."), { type: "danger" });
                    this.state.selectedPvzDisplay = pvzValue[1] || `ID: ${pvzValue[0]}`; // Fallback to display_name
                    this.state.currentInput = this.state.selectedPvzDisplay;
                } finally {
                    this.state.isLoading = false;
                }
            }
        } else {
            this.state.selectedPvzDisplay = "";
            this.state.currentInput = ""; // Очищаем инпут, если значение поля очищено
        }
    }

    _onInput(ev) {
        this.state.currentInput = ev.target.value;
        this.state.showDropdown = true;
        this.state.activeIndex = -1; // Сброс активного индекса при новом вводе
        if (this.state.currentInput.length >= 2) {
            this.debouncedSearch();
        } else {
            this.state.searchResults = [];
        }
    }

    async _performSearch() {
        if (this.state.currentInput.length < 2) {
            this.state.searchResults = [];
            this.state.showDropdown = false;
            return;
        }

        if (!this.state.defaultCountryCode) {
            // Можно добавить уведомление, если код страны не указан,
            // но поиск все равно может сработать без него, если так настроен бэкенд
            console.warn("CDEK PVZ Selector: Country code is not set. Searching without it.");
        }
        
        this.state.isLoading = true;
        try {
            const domain = [
                ['active', '=', true],
                ['city_name', 'ilike', this.state.defaultCityName || this.state.currentInput], // Поиск по городу из контекста или по вводу
                                                                                              // Либо, если хотим строго по городу из контекста И фильтр по названию/коду ПВЗ:
                                                                                              // ['city_name', 'ilike', this.state.defaultCityName],
                                                                                              // ['name', 'ilike', this.state.currentInput] // или code, или комбинация
            ];

            // Если defaultCityName задан, используем его строго, и ищем по currentInput в названии/коде ПВЗ
            // Если defaultCityName НЕ задан, ищем по currentInput в названии города
            if (this.state.defaultCityName) {
                domain.push(['city_name', 'ilike', this.state.defaultCityName]);
                // Добавляем поиск по currentInput в других полях ПВЗ, если город фиксирован
                domain.push('|', '|', 
                    ['name', 'ilike', this.state.currentInput],
                    ['code', 'ilike', this.state.currentInput],
                    ['address_full', 'ilike', this.state.currentInput]
                );
            } else {
                 domain.push(['city_name', 'ilike', this.state.currentInput]); // Если города нет, ищем город по вводу
            }


            if (this.state.defaultCountryCode) {
                domain.push(['country_code', '=', this.state.defaultCountryCode]);
            }

            const results = await this.orm.searchRead(
                'cdek.pvz',
                domain,
                ['id', 'code', 'name', 'address_full', 'city_name'], // city_name для информации
                { limit: 15 } // Ограничиваем количество результатов
            );
            this.state.searchResults = results;
            this.state.showDropdown = results.length > 0;
        } catch (error) {
            console.error("Error during CDEK PVZ search:", error);
            this.state.searchResults = [];
            this.state.showDropdown = false;
            this.notification.add(this.env._t("Error searching for PVZ."), { type: "danger" });
        } finally {
            this.state.isLoading = false;
        }
    }

    async _onPvzSelect(pvz) {
        this.state.showDropdown = false;
        this.state.searchResults = [];
        this.state.selectedPvzDisplay = `${pvz.code} - ${pvz.name} (${pvz.address_full})`;
        this.state.currentInput = this.state.selectedPvzDisplay; // Обновляем input после выбора

        // Обновляем основное поле cdek_pvz_id
        // this.props.update ожидает массив [id, display_name] или false
        // Мы можем передать просто ID, Odoo сам сделает name_get, если нужно
        // Либо передаем [id, строка_для_отображения_в_m2o]
        // Для простоты и чтобы Odoo обработал display_name стандартно:
        await this.props.update([{ id: pvz.id, display_name: `${pvz.code} - ${pvz.name}` }]);

        // Обновляем соседние поля в записи sale.order
        // Важно: this.props.record.update НЕ триггерит onchange на этих полях.
        // Если нужны onchange, то их надо вызывать вручную или ожидать,
        // что onchange сработает на cdek_pvz_id (если он настроен в Python).
        await this.props.record.update({
            cdek_pvz_code: pvz.code,
            cdek_pvz_name: pvz.name,
            cdek_pvz_address_full: pvz.address_full,
        });
         if (this.inputRef.el) {
            this.inputRef.el.focus(); // Вернуть фокус на инпут
        }
    }
    
    _onFocus() {
        // Можно показывать дропдаун с последними результатами или популярными, если currentInput пуст
        // Или если есть текст, но дропдаун был скрыт, показать его снова
        if (this.state.currentInput.length >= 2 && this.state.searchResults.length > 0) {
            this.state.showDropdown = true;
        } else if (this.state.currentInput.length >=2) { // Если есть текст, но нет результатов (например, после выбора)
            this.debouncedSearch(); // Попробовать поискать снова
        }
    }

    _onKeyDown(ev) {
        if (!this.state.showDropdown || this.state.searchResults.length === 0) {
            if (ev.key === "Enter" && this.state.currentInput && !this.props.record.data[this.props.name]) {
                // Если пользователь нажал Enter в инпуте, а значение не выбрано,
                // можно попробовать найти первое совпадение и выбрать его, либо ничего не делать.
                // Для простоты, если Enter и нет выделенного, ничего не делаем или ищем.
                this.debouncedSearch(); // Попробуем найти, если есть текст
            }
            return;
        }

        switch (ev.key) {
            case "ArrowDown":
                ev.preventDefault();
                this.state.activeIndex = (this.state.activeIndex + 1) % this.state.searchResults.length;
                this._scrollToActive();
                break;
            case "ArrowUp":
                ev.preventDefault();
                this.state.activeIndex = (this.state.activeIndex - 1 + this.state.searchResults.length) % this.state.searchResults.length;
                this._scrollToActive();
                break;
            case "Enter":
                ev.preventDefault();
                if (this.state.activeIndex !== -1) {
                    this._onPvzSelect(this.state.searchResults[this.state.activeIndex]);
                } else if (this.state.searchResults.length > 0) {
                    // Если ничего не выделено, но есть результаты, можно выбрать первый
                    // this._onPvzSelect(this.state.searchResults[0]);
                }
                break;
            case "Escape":
                ev.preventDefault();
                this.state.showDropdown = false;
                this.state.activeIndex = -1;
                break;
            case "Tab":
                this.state.showDropdown = false; // Скрыть дропдаун при Tab
                this.state.activeIndex = -1;
                break;
        }
    }
    
    _scrollToActive() {
        if (this.dropdownRef.el && this.state.activeIndex >= 0) {
            const activeButton = this.dropdownRef.el.querySelector(`.pvz-dropdown-item[data-index="${this.state.activeIndex}"]`);
            if (activeButton) {
                activeButton.scrollIntoView({ block: 'nearest' });
            }
        }
    }
    
    async _clearSelection(ev) {
        ev.stopPropagation(); // Предотвратить всплытие, если кнопка очистки внутри инпута или контейнера
        this.state.currentInput = "";
        this.state.searchResults = [];
        this.state.showDropdown = false;
        this.state.selectedPvzDisplay = "";
        
        await this.props.update(false); // Очищаем основное поле Many2one
        await this.props.record.update({ // Очищаем связанные поля
            cdek_pvz_code: false,
            cdek_pvz_name: false,
            cdek_pvz_address_full: false,
        });
        if (this.inputRef.el) {
            this.inputRef.el.focus();
        }
    }

    // Скрытие дропдауна при клике вне компонента
    _onClickOutside(ev) {
        if (this.root.el && !this.root.el.contains(ev.target)) {
            this.state.showDropdown = false;
            this.state.activeIndex = -1;
        }
    }
}

// Регистрация виджета в реестре полей
registry.category("fields").add("cdek_pvz_selector", CdekPvzSelector);