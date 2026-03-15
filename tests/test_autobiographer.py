import os
import unittest
import time
from unittest.mock import patch, MagicMock
import pandas as pd
from autobiographer import Autobiographer

class TestAutobiographer(unittest.TestCase):
    def setUp(self):
        self.api_key = "test_key"
        self.api_secret = "test_secret"
        self.username = "test_user"
        self.visualizer = Autobiographer(self.api_key, self.api_secret, self.username)

    @patch('requests.get')
    def test_fetch_recent_tracks(self, mock_get):
        # Mock response from Last.fm
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'recenttracks': {
                'track': [
                    {
                        'artist': {'#text': 'Artist 1'},
                        'album': {'#text': 'Album 1'},
                        'name': 'Track 1',
                        'date': {'uts': '1610000000', '#text': 'Date 1'}
                    }
                ],
                '@attr': {'totalPages': '1'}
            }
        }
        mock_get.return_value = mock_response

        tracks = self.visualizer.fetch_recent_tracks(pages=1)
        
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]['name'], 'Track 1')
        self.assertEqual(tracks[0]['artist']['#text'], 'Artist 1')

    @patch('requests.get')
    def test_fetch_page(self, mock_get):
        # Mock response from Last.fm
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'test': 'data'}
        mock_get.return_value = mock_response

        data = self.visualizer._fetch_page('user.getinfo', {})
        
        self.assertEqual(data, {'test': 'data'})
        mock_get.assert_called_once()

    def test_save_tracks_to_csv(self):
        # Sample data to save
        tracks = [
            {
                'artist': {'#text': 'Artist 1'},
                'album': {'#text': 'Album 1'},
                'name': 'Track 1',
                'date': {'uts': '1610000000', '#text': 'Date 1'}
            }
        ]
        test_filename = "data/test_tracks.csv"
        
        # Save to CSV
        self.visualizer.save_tracks_to_csv(tracks, filename=test_filename)
        
        # Verify file exists and content is correct
        self.assertTrue(os.path.exists(test_filename))
        df = pd.read_csv(test_filename)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['artist'], 'Artist 1')
        self.assertEqual(df.iloc[0]['track'], 'Track 1')
        
        # Cleanup
        os.remove(test_filename)

    @patch('requests.get')
    def test_fetch_recent_tracks_with_dates(self, mock_get):
        # Mock response from Last.fm
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'recenttracks': {
                'track': [],
                '@attr': {'totalPages': '1'}
            }
        }
        mock_get.return_value = mock_response

        self.visualizer.fetch_recent_tracks(from_ts=1610000000, to_ts=1610000100)
        
        # Verify that the correct parameters were passed to requests.get
        args, kwargs = mock_get.call_args
        params = kwargs.get('params', {})
        self.assertEqual(params.get('from'), 1610000000)
        self.assertEqual(params.get('to'), 1610000100)

    @patch('autobiographer.Autobiographer.fetch_recent_tracks')
    @patch('autobiographer.Autobiographer.save_tracks_to_csv')
    @patch('os.getenv')
    @patch('argparse.ArgumentParser.parse_args')
    def test_main_with_to_date(self, mock_args, mock_getenv, mock_save, mock_fetch):
        # Mock CLI arguments with a specific to_date
        mock_args.return_value = MagicMock(user='test_user', pages=None, from_date=None, to_date='2026-01-01')
        mock_getenv.side_effect = lambda k: {
            'AUTOBIO_LASTFM_API_KEY': 'key',
            'AUTOBIO_LASTFM_API_SECRET': 'secret',
            'AUTOBIO_LASTFM_USERNAME': 'test_user'
        }.get(k)
        
        from autobiographer import main
        main()
        
        # Verify to_ts is end of day for 2026-01-01
        # 2026-01-01 00:00:00 local timestamp + 86399
        expected_to_struct = time.strptime('2026-01-01', "%Y-%m-%d")
        expected_to_ts = int(time.mktime(expected_to_struct)) + 86399
        
        mock_fetch.assert_called_with(pages=None, from_ts=None, to_ts=expected_to_ts)

    @patch('autobiographer.Autobiographer.fetch_recent_tracks')
    @patch('autobiographer.Autobiographer.save_tracks_to_csv')
    @patch('os.getenv')
    @patch('argparse.ArgumentParser.parse_args')
    def test_main(self, mock_args, mock_getenv, mock_save, mock_fetch):
        # Mock CLI arguments and env vars
        mock_args.return_value = MagicMock(user='test_user', pages=1, from_date=None, to_date=None)
        mock_getenv.side_effect = lambda k: {
            'AUTOBIO_LASTFM_API_KEY': 'key',
            'AUTOBIO_LASTFM_API_SECRET': 'secret',
            'AUTOBIO_LASTFM_USERNAME': 'user'
        }.get(k)
        
        mock_fetch.return_value = []
        
        from autobiographer import main
        main()
        
        mock_fetch.assert_called_with(pages=1, from_ts=None, to_ts=None)
        mock_save.assert_called_once()

if __name__ == '__main__':
    unittest.main()

