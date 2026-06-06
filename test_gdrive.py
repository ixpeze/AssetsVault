import requests
import re

url = 'https://drive.google.com/uc?id=1sbWpYzQP4Fy_y638AeLRTcI5dBrnriJs&export=download'
session = requests.Session()
response = session.get(url, params={'confirm': 't'})
print('Initial Content-Type:', response.headers.get('Content-Type'))
if 'text/html' in response.headers.get('Content-Type', ''):
    match = re.search(r'<form[^>]+id=\"download-form\"[^>]+action=\"([^\"]+)\"', response.text, re.IGNORECASE)
    if not match:
        match = re.search(r'<form[^>]+action=\"([^\"]+)\"', response.text, re.IGNORECASE)
    
    print('Form action found:', match.group(1) if match else 'None')
    if match:
        action_url = match.group(1).replace('&amp;', '&')
        inputs = re.findall(r'<input[^>]+name=\"([^\"]+)\"[^>]+value=\"([^\"]*)\"', response.text)
        params = {k: v for k, v in inputs}
        print('Params:', params)
        final_resp = session.get(action_url, params=params, stream=True)
        print('Final Content-Type:', final_resp.headers.get('Content-Type'))
        print('Final Content-Disposition:', final_resp.headers.get('Content-Disposition'))
        print('Preview:', final_resp.raw.read(100))
