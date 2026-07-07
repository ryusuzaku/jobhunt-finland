import httpx
from bs4 import BeautifulSoup

r = httpx.get('https://www.academicwork.fi/avoimet-tyopaikat/j/hankintainsinoori-talotekniikka-tampere/8H01YQ', headers={'User-Agent': 'Mozilla/5.0'}, follow_redirects=True, timeout=20)
soup = BeautifulSoup(r.text, 'html.parser')
print('title:', soup.title.string.encode('ascii','ignore').decode() if soup.title else None)
text = soup.get_text('\n', strip=True)
print('first 1500 chars:', text[:1500].encode('ascii','ignore').decode())
