from unittest.mock import patch, MagicMock
from odoo.tests import common
from odoo.exceptions import UserError

class TestCdekAPI(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.api = self.env['cdek.api'].sudo()
        
        # Mock CDEK API responses
        self.mock_token_response = {
            'access_token': 'test_token',
            'token_type': 'Bearer',
            'expires_in': 3600
        }
        
        self.mock_tariff_response = {
            'entity': {
                'tariff_codes': [
                    {'code': 136, 'name': 'Стандарт'},
                    {'code': 438, 'name': 'Экспресс'}
                ]
            }
        }
        
        self.mock_calculation_response = {
            'entity': {
                'price': 500.0,
                'delivery_time': 3,
                'currency': 'RUB'
            }
        }
        
        self.mock_pvz_response = {
            'entity': [
                {
                    'code': 'PVZ1',
                    'name': 'Test PVZ 1',
                    'address': 'Test Address 1',
                    'latitude': 55.76,
                    'longitude': 37.64
                }
            ]
        }

    @patch('odoo.addons.cdek_integration.services.cdek_api.requests')
    def test_get_token(self, mock_requests):
        """Test OAuth2 token retrieval."""
        # Setup mock
        mock_response = MagicMock()
        mock_response.json.return_value = self.mock_token_response
        mock_requests.post.return_value = mock_response
        
        # Call method
        token = self.api.token
        
        # Assertions
        self.assertEqual(token, 'test_token')
        mock_requests.post.assert_called_once()

    @patch('odoo.addons.cdek_integration.services.cdek_api.requests')
    def test_list_tariffs(self, mock_requests):
        """Test tariff list retrieval."""
        # Setup mock
        mock_response = MagicMock()
        mock_response.json.return_value = self.mock_tariff_response
        mock_requests.get.return_value = mock_response
        
        # Call method
        tariffs = self.api.list_tariffs()
        
        # Assertions
        self.assertEqual(len(tariffs), 2)
        self.assertEqual(tariffs[0]['code'], 136)
        self.assertEqual(tariffs[1]['code'], 438)

    @patch('odoo.addons.cdek_integration.services.cdek_api.requests')
    def test_calculate_tariff(self, mock_requests):
        """Test tariff calculation."""
        # Setup mock
        mock_response = MagicMock()
        mock_response.json.return_value = self.mock_calculation_response
        mock_requests.post.return_value = mock_response
        
        # Test data
        from_location = {
            'code': '123456',
            'city': 'Moscow',
            'address': 'Test Street 1'
        }
        to_location = {
            'code': '654321',
            'city': 'St. Petersburg',
            'address': 'Test Street 2'
        }
        packages = [{
            'weight': 1.0,
            'length': 200,
            'width': 200,
            'height': 200
        }]
        
        # Call method
        result = self.api.calculate_tariff(
            tariff_code=136,
            from_location=from_location,
            to_location=to_location,
            packages=packages
        )
        
        # Assertions
        self.assertEqual(result['entity']['price'], 500.0)
        self.assertEqual(result['entity']['delivery_time'], 3)
        self.assertEqual(result['entity']['currency'], 'RUB')

    @patch('odoo.addons.cdek_integration.services.cdek_api.requests')
    def test_get_pvz_list(self, mock_requests):
        """Test PVZ list retrieval."""
        # Setup mock
        mock_response = MagicMock()
        mock_response.json.return_value = self.mock_pvz_response
        mock_requests.get.return_value = mock_response
        
        # Call method
        pvz_list = self.api.get_pvz_list(city_code='Moscow')
        
        # Assertions
        self.assertEqual(len(pvz_list), 1)
        self.assertEqual(pvz_list[0]['code'], 'PVZ1')
        self.assertEqual(pvz_list[0]['name'], 'Test PVZ 1')

    def test_error_handling(self):
        """Test error handling."""
        with self.assertRaises(UserError):
            self.api.token  # Should raise error when credentials not configured 