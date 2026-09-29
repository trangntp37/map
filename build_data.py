#!/usr/bin/env python3
"""
Đọc CSV xuất từ câu hỏi Metabase (query gộp store x giờ x thứ),
gộp thành data.json gọn cho trang bản đồ.

Cách dùng: python3 build_data.py raw.csv data.json
"""
import sys, json, re, os
import pandas as pd

def main(src, dst):
    df = pd.read_csv(src, dtype=str)

    for c in ['pickup_lat','pickup_lng','order_hour','weekday_iso',
              'total_orders','auto_cancel_orders']:
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', ''), errors='coerce')
    df = df.dropna(subset=['pickup_lat', 'pickup_lng'])

    PROV = {'BDG':'Bình Dương','DNI':'Đồng Nai','DAD':'Đà Nẵng','HPH':'Hải Phòng',
            'CXR':'Nha Trang','VCA':'Cần Thơ','DLI':'Đà Lạt','VII':'Vinh',
            'BMV':'Buôn Ma Thuột','VCS':'Vũng Tàu','HUI':'Huế','BNH':'Bắc Ninh',
            'LAN':'Long An','PXU':'Pleiku','THD':'Thanh Hóa','PHH':'Phan Thiết',
            'VDO':'Vân Đồn','TGG':'Tiền Giang'}
    BRAND = {'concung':'Con Cưng','pharmacity':'Pharmacity','longchau':'Long Châu',
             'ghnlastmile':'GHN Bưu cục','dienmayxanh':'MWG','bachhoaxanh':'Bách Hóa Xanh',
             'fpt':'FPT Shop','viettelpost':'Viettel Post','abbott':'Abbott',
             'aeonvn':'AEON','ahafoodai':'AhaFood AI','sme':'Khách lẻ (SME)'}

    def brand(pt, addr):
        if pt == 'dienmayxanh':
            m = re.match(r'^([^_]+)_', addr or '')
            return m.group(1).strip() if m else 'MWG'
        return BRAND.get(pt, pt)

    def head(addr, n=2):
        if not isinstance(addr, str):
            return ''
        parts = [p.strip() for p in re.split(r',| - ', addr) if p.strip()]
        parts = [p for p in parts if not re.search(
            r'(?i)^(phường|xã|thị trấn|tt\.|quận|huyện|tp\.?|thành phố|tỉnh|p\.|q\.|h\.|x\.|việt nam)', p)]
        return ', '.join(parts[:n]) if parts else addr[:40]

    def street(addr):
        if not isinstance(addr, str):
            return ''
        parts = [p.strip() for p in addr.split(',') if p.strip()]
        for p in parts[:3]:
            q = re.sub(r'^(Số|số|Lô|lô|Kios|Ki-ốt|Kiosk|Ô|Shop|Căn)\s*[\w/\-\.]*\s*', '', p).strip()
            q = re.sub(r'^[\d/\-\.A-Za-z]*\d[\w/\-\.]*\s+', '', q).strip()
            if re.search(r'(?i)^(phường|xã|thị trấn|tt\.|quận|huyện|tp|thành phố|tỉnh|p\.|q\.|h\.)', q):
                return ''
            if len(q) >= 3 and re.search(r'[A-Za-zÀ-ỹ]{2}', q) and not re.fullmatch(r'[\d\s/\-\.]+', q):
                return q
        return ''

    df['addr_clean'] = df.apply(
        lambda r: re.sub(r'^[^_]+_', '', r['pickup_address'])
        if r['partner'] == 'dienmayxanh' and isinstance(r['pickup_address'], str)
        else r['pickup_address'], axis=1)
    df['brand'] = df.apply(lambda r: brand(r['partner'], r['pickup_address']), axis=1)
    df['street'] = df['addr_clean'].apply(street)
    df['store_key'] = (df['pickup_lat'].round(4).astype(str) + ',' +
                        df['pickup_lng'].round(4).astype(str) + '|' + df['brand'])
    df['store_label'] = df['brand'] + ' – ' + df['addr_clean'].apply(head)
    df['ward'] = df['pickup_ward'].fillna('Không rõ').str.replace(
        '^Phường |^Xã |^Thị trấn ', '', regex=True)
    df['region'] = df['city_id'].map(PROV).fillna(df['city_id'])

    def mode_or_unknown(s):
        s = s.dropna()
        return s.value_counts().idxmax() if len(s) else 'Không rõ'

    store_info = df.groupby('store_key').agg(
        c=('city_id', 'first'), rg=('region', 'first'),
        w=('pickup_ward', mode_or_unknown),   # giá trị phổ biến nhất, bỏ qua dòng thiếu — không lấy máy móc dòng đầu
        st=('street', lambda s: mode_or_unknown(s.replace('', pd.NA))),
        b=('brand', 'first'), sl=('store_label', 'first'),
        lat=('pickup_lat', 'mean'), lng=('pickup_lng', 'mean'),
    ).reset_index()
    store_info['w'] = store_info['w'].astype(str).str.replace('^Phường |^Xã |^Thị trấn ', '', regex=True)
    sid = {k: i for i, k in enumerate(store_info.store_key)}

    cell = df.groupby(['store_key', 'order_hour', 'weekday_iso'], as_index=False).agg(
        n=('total_orders', 'sum'), ac=('auto_cancel_orders', 'sum'))
    cell['sid'] = cell.store_key.map(sid)

    stores = [None] * len(sid)
    for r in store_info.itertuples():
        stores[sid[r.store_key]] = [r.c, r.rg, r.w, r.st, r.b, r.sl,
                                     round(r.lat, 5), round(r.lng, 5)]
    cells = [[int(r.sid), int(r.order_hour), int(r.weekday_iso), int(r.n), int(r.ac)]
             for r in cell.itertuples()]

    payload = {'F': ['c', 'rg', 'w', 'st', 'b', 'sl', 'lat', 'lng'],
               'stores': stores, 'cells': cells}
    with open(dst, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    print(f'stores={len(stores)} cells={len(cells)} '
          f'size={os.path.getsize(dst)/1e6:.2f}MB '
          f'orders={sum(c[3] for c in cells)} auto_cancel={sum(c[4] for c in cells)}')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
