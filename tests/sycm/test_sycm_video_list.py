"""Offline regressions for list scope and nested evidence output; no data fetching."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'components/ali'))
from tb.platforms.sycm import item


class VideoListTests(unittest.TestCase):
 def test_raw_list_preserves_rows_and_records_real_coverage_in_nested_output(self):
  rows=[{'itemId':{'value':'1'},'statDate':{'value':1793635200000},'sellerId':{'value':1234567890}}]
  data={'recordCount':4983,'data':rows}
  class Cookies(dict):
   client=SimpleNamespace(_bridge_server=object())
  with tempfile.TemporaryDirectory() as directory:
   output=Path(directory)/'new'/'video.json'
   args=SimpleNamespace(date='2026-11-03',end_date='2026-11-03',limit=100,page=1,raw=True,out=str(output))
   with patch.object(item,'load_taobao_cookies',return_value=Cookies(_tb_token_='private')),patch.object(item,'_api_get',return_value={'data':data}),patch('tb.core.transport.release'),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
    item.cmd_video_list(args)
   result=json.loads(output.read_text(encoding='utf-8'))
   self.assertEqual(result['data'],rows);self.assertEqual(result['recordCount'],4983)
   self.assertFalse(result['coverage']['complete']);self.assertEqual(result['coverage']['actual_row_count'],1)
   self.assertNotIn('private',output.read_text(encoding='utf-8'))
   self.assertEqual(result['request']['params']['belongType'],'all')
 def test_video_list_rejects_unbounded_page_size_before_fetch(self):
  args=SimpleNamespace(date='2026-11-03',end_date='2026-11-03',limit=5000,page=1,raw=True,out=None)
  with patch.object(item,'load_taobao_cookies') as load:
   with self.assertRaises(ValueError):item.cmd_video_list(args)
   load.assert_not_called()

if __name__=='__main__':unittest.main()
