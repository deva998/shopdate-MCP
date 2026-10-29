import re
from ...core.platform import Platform

PAGE='https://jdsz.jd.com/szweb/view/tradeAnalysis/tradeSummary.html'
ENDPOINT='https://szgateway.jd.com/api/lowcode/tradeSummary/summary/getSummary.ajax'
JD=Platform(name='jd',display='京东商智',hosts={'api':ENDPOINT},login_page=PAGE,launch_url=PAGE,
 login_cookies=(),cookie_domains=(),referer=PAGE,expired_hints=(),write_re=re.compile('.*'),
 env_prefix='JD',extension_only=True,allow_post=True,bridge_posts=('/api/lowcode/tradeSummary/summary/getSummary.ajax',),min_extension='0.7.6')
