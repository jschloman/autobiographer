import unittest
import pandas as pd
import os
import shutil
import pydeck as pdk
from unittest.mock import patch, MagicMock
from record_flythrough import filter_data, create_recording_assets

class TestRecordFlythrough(unittest.TestCase):
    def setUp(self):
        self.test_dir = "data_test_fly"
        os.makedirs(self.test_dir, exist_ok=True)
        self.test_csv = os.path.join(self.test_dir, "test_tracks.csv")
        
        self.df = pd.DataFrame({
            'artist': ['Artist A', 'Artist B', 'Artist A'],
            'album': ['Album 1', 'Album 2', 'Album 1'],
            'track': ['Track 1', 'Track 2', 'Track 3'],
            'timestamp': [1610000000, 1610000100, 1610000200],
            'date_text': ['2021-01-01 10:00', '2021-01-01 10:01', '2021-01-01 11:02'],
            'lat': [41.0, 42.0, 41.0],
            'lng': [-87.0, -88.0, -87.0],
            'city': ['Reykjavik', 'Perth', 'Reykjavik']
        })
        self.df['date_text'] = pd.to_datetime(self.df['date_text'])
        self.df.to_csv(self.test_csv, index=False)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_filter_data_artist(self):
        filtered = filter_data(self.df, artist='Artist A')
        self.assertEqual(len(filtered), 2)
        self.assertTrue((filtered['artist'] == 'Artist A').all())

    def test_filter_data_dates(self):
        # All tracks are in 2021-01-01
        filtered = filter_data(self.df, start_date='2021-01-01 10:30')
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered.iloc[0]['track'], 'Track 3')

    def test_create_recording_assets_success(self):
        deck, keyframes = create_recording_assets(self.test_csv)
        self.assertIsNotNone(deck)
        self.assertIsInstance(deck, pdk.Deck)
        self.assertIsNotNone(keyframes)
        self.assertTrue(len(keyframes) >= 2)

    @patch('analysis_utils.load_swarm_data')
    @patch('analysis_utils.apply_swarm_offsets')
    @patch('os.path.exists')
    def test_create_recording_assets_geocoding_trigger(self, mock_exists, mock_apply, mock_load_swarm):
        # Create CSV without geodata
        no_geo_csv = os.path.join(self.test_dir, "no_geo.csv")
        self.df.drop(columns=['lat', 'lng', 'city']).to_csv(no_geo_csv, index=False)
        
        mock_load_swarm.return_value = pd.DataFrame({'timestamp': [1]})
        mock_apply.return_value = self.df # Return the one with geodata
        
        # Configure mock_exists to return True for the CSV and the swarm_dir
        def exists_side_effect(path):
            if path in [no_geo_csv, 'mock_swarm', 'default_assumptions.json']:
                return True
            return False
        mock_exists.side_effect = exists_side_effect
        
        create_recording_assets(no_geo_csv, swarm_dir='mock_swarm')
            
        self.assertTrue(mock_load_swarm.called)
        self.assertTrue(mock_apply.called)

if __name__ == '__main__':
    unittest.main()
