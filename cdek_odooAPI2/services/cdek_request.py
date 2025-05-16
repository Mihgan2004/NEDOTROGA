# -*- coding: utf-8 -*-
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from functools import cached_property # Для Odoo 15+
from odoo import _, fields # Добавил fields для datetime.to_iso_string при необходимости
from odoo.exceptions import UserError

# Убедитесь, что CDEK_URLS и REQUEST_TIMEOUT_SECONDS импортируются из вашего const.py
from ..const import CDEK_API_PROD_URL, CDEK_API_TEST_URL, CDEK_URLS, REQUEST_TIMEOUT_SECONDS

_logger = logging.getLogger(__name__)

class CdekRequest:
    def __init__(self, client_id, client_secret, base_url, debug_logger=None):
        if not all([client_id, client_secret, base_url]):
            # Эта проверка может быть избыточной, если _get_cdek_client в ResConfigSettings уже ее делает
            raise UserError(_("CDEK API credentials or Base URL are not configured."))

        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip('/') + '/' # Гарантируем один слэш в конце
        self._session = None
        self.debug_logger = debug_logger

    @cached_property
    def _access_token(self):
        url = self.base_url + CDEK_URLS["token"] # "oauth/token"
        payload = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        try:
            _logger.info("CDEK: Requesting new access token from %s", url)
            if self.debug_logger:
                self.debug_logger(f"POST {url}\nHeaders: {headers}\nPayload: {payload}", "cdek_token_request")

            # Используем self._get_session() для запроса токена тоже
            response = self._get_session().post(url, data=payload, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            token_data = response.json()

            if self.debug_logger:
                self.debug_logger(f"Status: {response.status_code}\nResponse: {token_data}", "cdek_token_response")

            if 'access_token' not in token_data:
                raise UserError(_("CDEK API: Access token not found in response. Response: %s") % token_data)
            _logger.info("CDEK: Successfully obtained new access token.")
            return token_data['access_token']
        except requests.exceptions.Timeout as e:
            _logger.error("CDEK API Timeout while fetching token: %s", e)
            raise UserError(_("CDEK API Timeout: Could not fetch access token in %s seconds.") % REQUEST_TIMEOUT_SECONDS) from e
        except requests.exceptions.RequestException as e:
            err_text = e.response.text if e.response else "No response"
            err_status = e.response.status_code if e.response else "N/A"
            _logger.error("CDEK API Error fetching token: %s, Status: %s, Response: %s", e, err_status, err_text)
            error_message = _("CDEK API Error: Could not fetch access token. Status: %s, Message: %s") % (err_status, err_text)
            raise UserError(error_message) from e

    def _clear_cached_token(self):
        if '_access_token' in self.__dict__: # Проверка для cached_property
            del self.__dict__['_access_token']
        _logger.info("CDEK: Cleared cached access token.")

    def _get_session(self):
        if not self._session:
            self._session = requests.Session()
            retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
            self._session.mount('https://', HTTPAdapter(max_retries=retries))
        return self._session

    def _request(self, method, endpoint_key, endpoint_params=None, json_payload=None, query_params=None, attempt_refresh=True):
        if endpoint_key not in CDEK_URLS:
            raise ValueError(f"Unknown CDEK endpoint key: {endpoint_key}")

        url_template = CDEK_URLS[endpoint_key]
        url = self.base_url + (url_template.format(**endpoint_params) if endpoint_params else url_template)

        headers = {'Content-Type': 'application/json'}
        # Поле 'Authorization' добавляется только если токен есть
        if hasattr(self, '_access_token'): # Проверка, что токен уже был запрошен (или будет запрошен)
             headers['Authorization'] = f'Bearer {self._access_token}'


        log_msg_payload = json_payload or query_params or {}
        _logger.info("CDEK API Request: %s %s", method.upper(), url)
        _logger.debug("CDEK API Request Headers: %s, Payload: %s", headers, log_msg_payload)

        if self.debug_logger:
            self.debug_logger(f"{method.upper()} {url}\nHeaders: {headers}\nPayload: {log_msg_payload}", "cdek_api_request")

        try:
            response = self._get_session().request(
                method, url,
                json=json_payload, # Для POST/PUT/PATCH с JSON телом
                params=query_params,   # Для GET с параметрами в URL
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            
            # Для запросов, возвращающих бинарные данные (например, этикетки), json() вызовет ошибку
            if response.headers.get('Content-Type', '').lower() in ['application/pdf', 'application/zpl', 'text/plain', 'application/octet-stream']:
                response_data_for_log = f"Binary Content, Type: {response.headers.get('Content-Type')}, Length: {len(response.content)}"
                response_to_return = response.content # Возвращаем бинарные данные напрямую
            else:
                response_data_for_log = response.json() if response.content else {}
                response_to_return = response_data_for_log

            if self.debug_logger:
                self.debug_logger(f"Status: {response.status_code}\nResponse: {response_data_for_log}", "cdek_api_response")
            _logger.debug("CDEK API Response: Status %s, Data: %s", response.status_code, response_data_for_log)

            # Обработка стандартной структуры ошибок CDEK API v2, если ответ - JSON
            if isinstance(response_to_return, dict):
                # Иногда ошибки приходят в корне объекта
                if response_to_return.get('errors'):
                    self._handle_cdek_errors(response_to_return['errors'])
                
                # Иногда ответ завернут в 'requests' (особенно при пакетных запросах или асинхронных операциях)
                # или есть 'entity' для успешных ответов
                api_requests = response_to_return.get('requests')
                if api_requests and isinstance(api_requests, list) and api_requests[0].get('errors'):
                    self._handle_cdek_errors(api_requests[0]['errors'])
                
                # Если есть 'entity', это обычно успешный ответ на создание/получение
                if 'entity' in response_to_return:
                    return response_to_return['entity']
                # Для калькулятора ответ может быть не в 'entity'
                if endpoint_key == 'calculator_tariff' and 'total_sum' in response_to_return:
                    return response_to_return # Возвращаем весь объект ответа калькулятора

            return response_to_return # Возвращаем либо JSON dict, либо bytes

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401 and attempt_refresh:
                _logger.warning("CDEK API: Received 401 Unauthorized for %s. Attempting to refresh token.", url)
                self._clear_cached_token()
                return self._request(method, endpoint_key, endpoint_params, json_payload, query_params, attempt_refresh=False)

            err_text = e.response.text if e.response else "No response text"
            _logger.error("CDEK API HTTPError: %s %s, Status: %s, Response: %s",
                          method.upper(), url, e.response.status_code, err_text)
            try:
                error_data = e.response.json()
                if error_data.get('errors'):
                    self._handle_cdek_errors(error_data['errors']) # _handle_cdek_errors сам поднимет UserError
                elif error_data.get('requests') and error_data['requests'][0].get('errors'):
                    self._handle_cdek_errors(error_data['requests'][0]['errors'])
                else:
                    raise UserError(_("CDEK API Error: %s. Details: %s") % (e.response.status_code, err_text))
            except (ValueError, UserError) as parsing_or_handled_error: # Если не JSON или UserError уже поднят
                if isinstance(parsing_or_handled_error, UserError):
                    raise
                raise UserError(_("CDEK API Error: %s. Response not in expected JSON error format: %s") % (e.response.status_code, err_text)) from e
            except Exception as final_e: # Непредвиденная ошибка при парсинге ошибки
                 _logger.error("CDEK API: Failed to parse error response for HTTPError: %s", final_e)
                 raise UserError(_("CDEK API Error: %s. Details: %s") % (e.response.status_code, err_text)) from e

        except requests.exceptions.Timeout as e:
            _logger.error("CDEK API Timeout: %s %s. %s", method.upper(), url, e)
            raise UserError(_("CDEK API Timeout: The request to %s took longer than %s seconds.") % (url, REQUEST_TIMEOUT_SECONDS)) from e
        except requests.exceptions.RequestException as e: # Другие ошибки requests (сеть и т.д.)
            _logger.error("CDEK API RequestException: %s %s. %s", method.upper(), url, e)
            raise UserError(_("CDEK API communication error: %s") % e) from e

    def _handle_cdek_errors(self, errors_list):
        error_messages = []
        for error in errors_list:
            msg = f"Code: {error.get('code')}, Message: {error.get('message')}"
            if error.get('field'):
                msg += f" (Field: {error.get('field')})"
            error_messages.append(msg)
            _logger.error("CDEK API Error Detail: %s, Details: %s", msg, error.get('details'))
        raise UserError(_("CDEK API Error(s):\n%s") % "\n".join(error_messages))

    # --- Публичные методы для вызова из моделей Odoo ---
    def create_order(self, payload):
        _logger.info("CDEK: Creating order with payload.") # Не логгируем сам payload здесь из-за PII
        _logger.debug("CDEK: Creating order with payload: %s", payload)
        return self._request('POST', 'orders', json_payload=payload) # Вернет 'entity'

    def get_order_info(self, order_uuid):
        _logger.info("CDEK: Getting order info for UUID: %s", order_uuid)
        return self._request('GET', 'order_by_uuid', endpoint_params={'uuid': order_uuid}) # Вернет 'entity'

    def calculate_tariff(self, payload):
        _logger.info("CDEK: Calculating tariff.")
        _logger.debug("CDEK: Calculating tariff with payload: %s", payload)
        # Этот метод вернет весь JSON ответа калькулятора, а не только 'entity'
        return self._request('POST', 'calculator_tariff', json_payload=payload)

    def get_delivery_points(self, params=None):
        _logger.info("CDEK: Getting delivery points with params: %s", params)
        return self._request('GET', 'delivery_points', query_params=params) # Это вернет список ПВЗ

    def get_cities(self, params=None):
        _logger.info("CDEK: Getting cities with params: %s", params)
        return self._request('GET', 'location_cities', query_params=params) # Это вернет список городов

    def get_label_data(self, order_uuid, label_format='pdf'):
        if label_format.lower() not in ['pdf', 'zpl']: # Приводим к нижнему регистру для сравнения
            raise ValueError(_("Unsupported label format: %s. Use 'pdf' or 'zpl'.") % label_format)
        _logger.info("CDEK: Getting %s label for order UUID: %s", label_format.upper(), order_uuid)
        # Этот метод вернет бинарные данные (bytes)
        return self._request('GET', 'print_barcodes', endpoint_params={'uuid': order_uuid, 'format': label_format.lower()})