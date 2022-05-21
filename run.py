from itertools import groupby
import os
import time
from typing import Any, Callable, TypeVar
from xml.sax.saxutils import escape
import pdfplumber
import json
import googlemaps
import geopy.distance

def outputJsonFile(file_name: str, value, minimum: bool = False) -> None:
    with open(file_name, 'w', encoding='utf_8') as f:
      separators = (',',':') if minimum else None
      indent = None if minimum else 2
      f.write(json.dumps(value, ensure_ascii=False, separators=separators, indent=indent))

def inputJsonFile(file_name: str) -> Any:
    with open(file_name, 'r', encoding='utf_8') as f:
        return json.load(f)

T = TypeVar('T')

def cacheJsonFile(file_name: str, on_create: Callable[[], T]) -> T:
    if not os.path.exists(file_name):
        outputJsonFile(file_name, on_create())
    return inputJsonFile(file_name)

def extractTable(pdf: pdfplumber.PDF):
    data: list[list[str | None]] = []
    for page in pdf.pages:
        print(f'page: {page.page_number}')
        table = page.extract_table()
        data.extend(table[2:])
    return data

gmaps = googlemaps.Client(key=inputJsonFile('./apikey.json'))
geo_offset_distance = geopy.distance.GeodesicDistance(meters=3)

def find_place(text: str):
  result = gmaps.find_place(
    text,
    input_type='textquery',
    fields=['business_status','formatted_address','geometry','icon','name','photos','place_id','plus_code','types'],
    language='ja',
    location_bias=f'rectangle:35.1598723715222,138.82338748509508|37.16621915151721,137.27180990577534'
  )
  time.sleep(0.2)
  return result

def text_to_latlng(text: str):
  arr = [float(x) for x in text.split(',')]
  assert len(arr) == 2
  assert arr[0]
  assert arr[1]
  return {
    "lat": arr[0],
    "lng": arr[1],
  }

if not os.path.exists('./results'): os.mkdir('./results')
if not os.path.exists('./geo'): os.mkdir('./geo')

geoFixs: dict = inputJsonFile('./geo-fix_updated.json')

print('open')
with pdfplumber.open('./list-k-adv.pdf') as pdf:
    # ハイパーリンク
    links = [x['uri'] for x in pdf.hyperlinks]
    print(f'links: {len(links)}')

    # すべてのテーブルを取得
    data = cacheJsonFile('./results/table_values.json', lambda: extractTable(pdf))

    # Noの重複確認
    assert len(data) == len(set(map(lambda v: v[0], data)))
    
    # "HP"をリンクに置き換え
    linkIndex = 0
    for values in data:
        if values[7] == 'HP':
            values[7] = links[linkIndex]
            linkIndex += 1

    assert linkIndex == len(links)

    # 市町村名と施設名で重複除去
    data.sort(key=lambda d: d[2] + '||' + d[3]) # キーで事前ソート
    data = [next(group[1]) for group in groupby(data, lambda d: d[2] + '||' + d[3])]
    data.sort(key=lambda d: int(d[0])) # 番号順に戻す

    for values in data:
        print(f'geo: {values[0]} {values[2]} {values[3]} {values[5]} {values[6]} {values[7]}')
        geoFix: dict | None = geoFixs[values[0]] if values[0] in geoFixs else None
        location: dict | None = { "lat": geoFix['lat'], "lng": geoFix['lng'] } if geoFix and 'lat' in geoFix else None
        check_addr = geoFix['addr'] if geoFix and 'addr' in geoFix else True
        distance: float = 0
        if not location:
            geo = cacheJsonFile(f'./geo/{values[0]}.json', lambda: find_place(f'{values[2]} {values[3]}'))['candidates']
            geo_addr = cacheJsonFile(f'./geo/{values[0]}_addr.json', lambda: find_place(f'長野県{values[5]}'))['candidates']
            if len(geo) >= 1 and '長野県' in geo[0]['formatted_address'] and values[2] in geo[0]['formatted_address']:
              location = geo[0]['geometry']['location']
              if check_addr:
                if len(geo_addr) > 0:
                  addr_location = geo_addr[0]['geometry']['location']
                  distance = geopy.distance.distance((location['lat'], location['lng']), (addr_location['lat'], addr_location['lng'])).m
                  print((location['lat'], location['lng']), (addr_location['lat'], addr_location['lng']), distance)
                  # assert 0 <= distance and distance < 500
                else:
                  print((location['lat'], location['lng']))
                  yes_or_latlng = input('address not found. ignore? ["y" or lat,lng]: ')
                  if yes_or_latlng == 'y':
                    geoFixs[values[0]] = { "addr": False }
                  else:
                    location = text_to_latlng(yes_or_latlng)
                    geoFixs[values[0]] = location
                  outputJsonFile('./geo-fix_updated.json', geoFixs)
            else:
              if len(geo) >= 1:
                v = geo[0]['geometry']['location']
                print((v['lat'], v['lng']))
              latlngInputText = input('Lat,Lng: ')
              location = text_to_latlng(latlngInputText)
              geoFixs[values[0]] = location
              outputJsonFile('./geo-fix_updated.json', geoFixs)
        values.append(location['lat'])
        values.append(location['lng'])
        values.append(distance)

    outputJsonFile('./results/data.json', data)

    # 北にオフセットする（Googleマップのマーカーと衝突を防ぐ）
    for values in data:
      pt = geopy.distance.Point(values[12], values[13])
      pt: geopy.distance.Point = geo_offset_distance.destination(pt, bearing=0) #北にオフセット
      values[12] = pt.latitude
      values[13] = pt.longitude

    groups = groupby(data, key=lambda d: d[1])

    def to_placemark(values: list[str]):
      return f'''
      <Placemark>
        <name>{escape(values[3])}</name>
        <description><![CDATA[No.{values[0]}<br>長野県{values[5]}<br>{values[6]}<br>{values[7]}<br>{values[8]}<br>{'<br>'.join(filter(lambda v: v != '', values[9:12]))}]]></description>
        <styleUrl>#icon-1899-0288D1</styleUrl>
        <Point><coordinates>{values[13]},{values[12]},0</coordinates></Point>
      </Placemark>
'''

    def to_folder(layer_name: str, data: list[list[str | None]]):
      print(layer_name, len(data))
      return f'''
    <Folder>
      <name>{layer_name}</name>
{''.join([to_placemark(values) for values in data])}
    </Folder>
'''

    for group in groups:
      folder = to_folder(group[0], list(group[1]))
      with open(f'./results/result_{group[0]}.kml', 'w', encoding='utf_8') as f:
        f.write(f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>信州割クーポン対象店舗 ({group[0]})</name>
    <description/>
    <Style id="icon-1899-0288D1-normal">
      <IconStyle>
        <color>ffd18802</color>
        <scale>1</scale>
        <Icon>
          <href>https://www.gstatic.com/mapspro/images/stock/503-wht-blank_maps.png</href>
        </Icon>
        <hotSpot x="32" xunits="pixels" y="64" yunits="insetPixels"/>
      </IconStyle>
      <LabelStyle>
        <scale>0</scale>
      </LabelStyle>
    </Style>
    <Style id="icon-1899-0288D1-highlight">
      <IconStyle>
        <color>ffd18802</color>
        <scale>1</scale>
        <Icon>
          <href>https://www.gstatic.com/mapspro/images/stock/503-wht-blank_maps.png</href>
        </Icon>
        <hotSpot x="32" xunits="pixels" y="64" yunits="insetPixels"/>
      </IconStyle>
      <LabelStyle>
        <scale>1</scale>
      </LabelStyle>
    </Style>
    <StyleMap id="icon-1899-0288D1">
      <Pair>
        <key>normal</key>
        <styleUrl>#icon-1899-0288D1-normal</styleUrl>
      </Pair>
      <Pair>
        <key>highlight</key>
        <styleUrl>#icon-1899-0288D1-highlight</styleUrl>
      </Pair>
    </StyleMap>
{folder}
  </Document>
</kml>''')
