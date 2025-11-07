from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import os

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise SystemExit('DATABASE_URL not set')

url = urlparse(DATABASE_URL)
query = parse_qs(url.query)
query['sslmode'] = ['require']
url = url._replace(query=urlencode(query, doseq=True), netloc='db.sdperhhkntsfzdckpynl.supabase.co:6543')
print(urlunparse(url))
