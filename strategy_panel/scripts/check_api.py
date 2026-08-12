import urllib.request, json

r = urllib.request.urlopen('http://localhost:8100/api/strategies')
data = json.loads(r.read())
print('Strategies:')
for s in data:
    print(f'  {s["id"]}: {list(s.keys())}')
    print(f'    val: {round(s["annualReturn"]*100,2)}%')

r2 = urllib.request.urlopen('http://localhost:8100/api/overview')
d2 = json.loads(r2.read())
f = d2.get('folio', {})
if f:
    print(f'\nFolio: {round(f["annualReturn"]*100,2)}% | Sharpe {f["sharpe"]}')
    print(f'  Weights: {f.get("weights", {})}')
else:
    print('\nNo folio')
