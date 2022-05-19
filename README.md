# 信州割の観光クーポン対象店舗のPDFをKMLに変換してGoogle My Mapsで表示する

## 環境
```
pip install pdfminer.six
pip install pdfplumber
pip install googlemaps
pip install geopy
```

## APIキー
Google Geocoding API のAPIキーを apikey.json に書き込む。

```json
"<API-KEY>"
```
## 実行
```
py ./run.py
```

## Google My Maps
レイヤを追加して1ファイルずつインポートする。
