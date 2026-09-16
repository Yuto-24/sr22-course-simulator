"""Common Notebook contract and an optional end-to-end execution check."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from xml.etree import ElementTree as ET

NOTEBOOK = Path(__file__).resolve().parents[1] / 'notebooks/kyushu_traffic_patterns.ipynb'


class KyushuNotebookTests(unittest.TestCase):
    def test_clean_notebook_and_single_parameter_cell(self):
        notebook = json.loads(NOTEBOOK.read_text())
        self.assertEqual(notebook['metadata']['kernelspec']['name'], 'python3')
        parameters = [c for c in notebook['cells'] if 'parameters' in c['metadata'].get('tags', [])]
        self.assertEqual(len(parameters), 1)
        namespace = {}
        exec(''.join(parameters[0]['source']), namespace)
        self.assertEqual(namespace['AIRPORT'], 'RJFM')
        self.assertIs(namespace['EXPORT_ALL_AIRPORTS'], True)
        switches = [key for key in namespace if key.startswith('MAKE_')]
        self.assertEqual(len(switches), 5)
        self.assertTrue(all(type(namespace[key]) is bool for key in switches))
        for index, cell in enumerate(notebook['cells']):
            if cell['cell_type'] == 'code':
                self.assertIsNone(cell['execution_count'])
                self.assertEqual(cell['outputs'], [])
                compile(''.join(cell['source']), f'kyushu-cell-{index}', 'exec')

    @unittest.skipUnless(importlib.util.find_spec('matplotlib') and importlib.util.find_spec('IPython'),
                         'Notebook execution requires optional notebook dependencies')
    def test_selected_airport_parameters_drive_plots_and_exports(self):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        notebook = json.loads(NOTEBOOK.read_text())
        namespace = {}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'SR22_ARTIFACT_DIR': directory}), contextlib.redirect_stdout(io.StringIO()):
            try:
                for cell in notebook['cells']:
                    if cell['cell_type'] != 'code':
                        continue
                    exec(''.join(cell['source']), namespace)
                    if 'parameters' in cell['metadata'].get('tags', []):
                        namespace['AIRPORT'] = 'RJFT'
                        namespace['EXPORT_ALL_AIRPORTS'] = False
                        for key in tuple(namespace):
                            if key.startswith('MAKE_'):
                                namespace[key] = False
                self.assertEqual(len(namespace['profile_rows']), 4)
                self.assertEqual({row[1] for row in namespace['profile_rows']}, {1400, 1700})
                self.assertEqual(len(namespace['figure'].axes), 8)
                for axis in namespace['figure'].axes[1::2]:
                    self.assertEqual(axis.get_ylabel(), 'Altitude MSL [ft]')
                    self.assertEqual(len(axis.lines), 1)
                self.assertEqual(len(namespace['written']), 6)
                kmz = Path(directory) / 'kyushu-traffic-patterns/RJFT_TRAFFIC_PATTERNS.kmz'
                with ZipFile(kmz) as archive:
                    root = ET.fromstring(archive.read('doc.kml'))
                self.assertEqual(len(root.findall('.//{http://www.opengis.net/kml/2.2}Placemark')), 4)
            finally:
                plt.close('all')
