import unittest,json
from tb.platforms.sycm import market_discovery as m

class MarketDiscoveryTests(unittest.TestCase):
 def test_only_declared_qianniu_pages(self):
  self.assertEqual(len(m.RECRUIT_PAGES),6)
  self.assertIn('qn-tmc-bidding',m.RECRUIT_PAGES['seller'])
  with self.assertRaises(ValueError):m.recruit_url('https://evil.example')
 def test_native_page_summary_never_persists_signed_html(self):
  html='<html><script src="https://g.alicdn.com/qn/app.js?token=SECRET"></script><script>window.token="PRIVATE";var method="mtop.foo.query";</script></html>'
  r=m.source_summary(html,m.RECRUIT_PAGES['seller'])
  self.assertEqual(r['status'],'definition_only');self.assertFalse(r['business_statistics_verified']);self.assertEqual(r['scripts'],['https://g.alicdn.com/qn/app.js']);self.assertNotIn('SECRET',json.dumps(r));self.assertNotIn('PRIVATE',json.dumps(r))
 def test_security_and_login_are_not_empty_business_reports(self):
  self.assertEqual(m.source_summary('<html>_____tmd_____ x5secdata=SECRET</html>',m.RECRUIT_PAGES['seller'])['status'],'security_verification')
  self.assertEqual(m.source_summary('<input type="password">',m.RECRUIT_PAGES['seller'])['status'],'login_required')

if __name__=='__main__':unittest.main()
