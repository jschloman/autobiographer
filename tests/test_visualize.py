import unittest
import pandas as pd
import os
import shutil
from unittest.mock import patch, MagicMock, ANY
from visualize import render_top_charts, render_timeline_analysis, render_spatial_analysis, render_insights_and_narrative, main
from analysis_utils import load_listening_data

class TestVisualize(unittest.TestCase):
    def setUp(self):
        self.test_dir = "data_test"
        os.makedirs(self.test_dir, exist_ok=True)
        self.test_csv = os.path.join(self.test_dir, "test_user_tracks.csv")
        
        self.df = pd.DataFrame({
            'artist': ['Artist 1', 'Artist 2', 'Artist 1'],
            'album': ['Album 1', 'Album 2', 'Album 1'],
            'track': ['Track 1', 'Track 2', 'Track 3'],
            'timestamp': [1610000000, 1610000100, 1610000200],
            'date_text': ['2021-01-01 10:00', '2021-01-01 10:01', '2021-01-01 11:02'],
            'lat': [41.0, 42.0, 41.0],
            'lng': [-87.0, -88.0, -87.0],
            'city': ['Reykjavik', 'Perth', 'Reykjavik'],
            'state': ['IS', 'WA', 'IS'],
            'country': ['Iceland', 'Australia', 'Iceland']
        })
        self.df['date_text'] = pd.to_datetime(self.df['date_text'])
        self.df.to_csv(self.test_csv, index=False)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    @patch('streamlit.header')
    @patch('streamlit.selectbox')
    @patch('streamlit.date_input')
    @patch('streamlit.columns')
    @patch('streamlit.pydeck_chart')
    @patch('streamlit.dataframe')
    @patch('streamlit.slider')
    def test_render_spatial_analysis(self, mock_slider, mock_df, mock_deck, mock_cols, mock_date, mock_select, mock_header):
        mock_select.return_value = 'All'
        mock_date.return_value = [self.df['date_text'].min().date(), self.df['date_text'].max().date()]
        mock_cols.side_effect = [
            [MagicMock(), MagicMock()], # col_f1, col_f2
            [MagicMock(), MagicMock(), MagicMock()], # col_a, col_b, col_c
            [MagicMock(), MagicMock()] # fly_col1, fly_col2
        ]
        mock_slider.return_value = 3.0
        
        mock_state = MagicMock()
        mock_state.__contains__.return_value = False
        
        with patch('streamlit.session_state', mock_state):
            render_spatial_analysis(self.df)
        
        mock_header.assert_called_with("Spatial Music Explorer")
        mock_deck.assert_called_once()
        mock_df.assert_called_once()

    @patch('streamlit.header')
    @patch('streamlit.radio')
    @patch('streamlit.slider')
    @patch('streamlit.columns')
    @patch('streamlit.plotly_chart')
    def test_render_top_charts(self, mock_plotly, mock_columns, mock_slider, mock_radio, mock_header):
        mock_radio.return_value = 'artist'
        mock_slider.return_value = 10
        mock_columns.return_value = [MagicMock(), MagicMock()]
        
        render_top_charts(self.df)
        
        mock_header.assert_called_with("Top Charts")
        self.assertEqual(mock_plotly.call_count, 2)
        mock_plotly.assert_any_call(ANY, width='stretch')

    @patch('streamlit.header')
    @patch('streamlit.selectbox')
    @patch('streamlit.plotly_chart')
    @patch('streamlit.subheader')
    def test_render_timeline_analysis(self, mock_subheader, mock_plotly, mock_selectbox, mock_header):
        mock_selectbox.return_value = 'Daily'
        
        render_timeline_analysis(self.df)
        
        mock_header.assert_called_with("Activity Over Time")
        self.assertEqual(mock_plotly.call_count, 2)
        mock_plotly.assert_any_call(ANY, width='stretch')

    @patch('streamlit.header')
    @patch('streamlit.subheader')
    @patch('streamlit.selectbox')
    @patch('streamlit.columns')
    @patch('streamlit.plotly_chart')
    @patch('streamlit.dataframe')
    @patch('streamlit.tabs')
    @patch('streamlit.metric')
    def test_render_insights_and_narrative(self, mock_metric, mock_tabs, mock_df, mock_plotly, mock_cols, mock_select, mock_subheader, mock_header):
        mock_select.return_value = 'All'
        # Provide lists for each st.columns call
        mock_cols.side_effect = [
            [MagicMock()] * 4, # col_filter1-4
            [MagicMock()] * 2, # col_top1-2
            [MagicMock()] * 2, # col_pat1-2
            [MagicMock()] * 2  # col_nar1-2
        ]
        mock_tabs.return_value = [MagicMock(), MagicMock(), MagicMock()]
        
        render_insights_and_narrative(self.df)
        
        mock_header.assert_called_with("Insights & Narrative")
        self.assertTrue(mock_select.called)

    @patch('streamlit.set_page_config')
    @patch('streamlit.title')
    @patch('streamlit.sidebar.selectbox')
    @patch('visualize.load_listening_data')
    @patch('streamlit.tabs')
    @patch('streamlit.sidebar.header')
    @patch('streamlit.sidebar.text_input')
    @patch('streamlit.sidebar.date_input')
    @patch('streamlit.sidebar.button')
    @patch('streamlit.spinner')
    def test_main_success(self, mock_spinner, mock_button, mock_date_input, mock_text_input, mock_sidebar_header, mock_tabs, mock_load, mock_selectbox, mock_title, mock_config):
        original_exists = os.path.exists
        mock_date_input.return_value = [self.df['date_text'].min().date(), self.df['date_text'].max().date()]
        mock_button.return_value = False
        
        mock_spinner.return_value.__enter__.return_value = None
        mock_spinner.return_value.__exit__.return_value = None
        
        with patch('os.listdir') as mock_listdir, \
             patch('visualize.render_top_charts'), \
             patch('visualize.render_timeline_analysis'), \
             patch('visualize.render_spatial_analysis'), \
             patch('visualize.render_insights_and_narrative'):
            
            with patch('os.path.exists') as mock_exists:
                def side_effect(path):
                    if path == 'data': return True
                    if path == 'default_assumptions.json.example': return True
                    return original_exists(path)
                mock_exists.side_effect = side_effect
                
                mock_listdir.return_value = ['test_user_tracks.csv']
                mock_selectbox.return_value = 'test_user_tracks.csv'
                mock_text_input.side_effect = ['data', '', 'default_assumptions.json.example']
                mock_load.return_value = self.df
                
                # Updated to 4 tabs
                tab1, tab2, tab3, tab4 = MagicMock(), MagicMock(), MagicMock(), MagicMock()
                mock_tabs.return_value = [tab1, tab2, tab3, tab4]
                
                main()
        
        mock_title.assert_called_with("Autobiographer: Interactive Data Explorer")
        mock_load.assert_called_once()
        self.assertEqual(len(mock_tabs.return_value), 4)
        self.assertTrue(mock_date_input.called)

if __name__ == '__main__':
    unittest.main()

