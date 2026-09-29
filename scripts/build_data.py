"""Dựng data.json cho trang heatmap hex từ file export 14 ngày (data_14d.csv).
Chạy:  python scripts/build_data.py data_14d.csv data.json
Cần:   pip install pandas h3

CSV cần các cột: city_id, pickup_lat, pickup_lng, pickup_ward, pickup_street, order_date_vn,
                 order_hour, weekday_iso, total_orders, auto_cancel_orders
(cột khác nếu có sẽ bị bỏ qua)

Đầu ra (trang chỉ hiển thị lưới hex, không có cửa hàng / brand / địa chỉ / tọa độ):
  F      = ["c","rg","w","st","hx"]
  stores = 1 dòng / (tỉnh, phường, đường, ô hex); đường trống = không nhận ra tên đường
  cells  = [id dòng, giờ, thứ(1=T2..7=CN), tổng đơn, đơn bị bỏ lỡ]
Đơn bị bỏ lỡ = auto_cancel_orders (không tài xế nào nhận).
hx = mã H3 res 8 (~0,74 km²/ô) tính từ pickup_lat/lng.
"""
import re, sys, json
import pandas as pd
import h3

HEX_RES = 8

# Tên vùng ngắn (cột rg)
RG = {'BDG': 'Bình Dương', 'DNI': 'Đồng Nai', 'DAD': 'Đà Nẵng', 'HPH': 'Hải Phòng', 'CXR': 'Nha Trang',
      'VCA': 'Cần Thơ', 'DLI': 'Đà Lạt', 'VII': 'Vinh', 'BMV': 'Buôn Ma Thuột', 'VCS': 'Vũng Tàu',
      'HUI': 'Huế', 'BNH': 'Bắc Ninh', 'LAN': 'Long An', 'PXU': 'Pleiku', 'THD': 'Thanh Hóa',
      'PHH': 'Phan Thiết', 'VDO': 'Vân Đồn', 'TGG': 'Tiền Giang'}
WARD_PREFIX = re.compile(r'^(phường|xã|thị trấn|đặc khu)\s+', re.I)


def main(src, dst):
    df = pd.read_csv(src)
    days = df['order_date_vn'].nunique()

    # hex res 8 cho từng tọa độ (tính 1 lần / tọa độ cho nhanh)
    pts = df[['pickup_lat', 'pickup_lng']].drop_duplicates()
    pts['hx'] = [h3.latlng_to_cell(float(a), float(b), HEX_RES) for a, b in zip(pts.pickup_lat, pts.pickup_lng)]
    df = df.merge(pts, on=['pickup_lat', 'pickup_lng'], how='left')

    df['w'] = (df['pickup_ward'].fillna('Không rõ').astype(str)
               .map(lambda x: WARD_PREFIX.sub('', x).strip() or 'Không rõ'))
    if 'pickup_street' in df.columns:
        df['st'] = df['pickup_street'].fillna('').astype(str).str.strip()
    else:
        df['st'] = ''
    key = ['city_id', 'w', 'st', 'hx']
    df['uid'] = df.groupby(key, sort=True).ngroup()

    units = df.drop_duplicates('uid').sort_values('uid')
    stores = [[r.city_id, RG.get(r.city_id, r.city_id), r.w, r.st, r.hx] for r in units.itertuples()]

    g = (df.groupby(['uid', 'order_hour', 'weekday_iso'])[['total_orders', 'auto_cancel_orders']]
           .sum().reset_index())
    cells = g.astype(int).values.tolist()

    out = {'F': ['c', 'rg', 'w', 'st', 'hx'], 'stores': stores, 'cells': cells}
    json.dump(out, open(dst, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))

    # kiểm tra: tổng đơn và đơn bỏ lỡ phải khớp file gốc
    assert g.total_orders.sum() == df.total_orders.sum()
    assert g.auto_cancel_orders.sum() == df.auto_cancel_orders.sum()
    print(f'{days} ngày ({df.order_date_vn.min()} → {df.order_date_vn.max()}) · '
          f'{df.hx.nunique()} hex res {HEX_RES} · {len(stores)} dòng hex×phường×đường · có tên đường: {(df.st != '').mean():.0%} số dòng · {len(cells)} cell · '
          f'tổng đơn khớp: {int(g.total_orders.sum())} · bỏ lỡ khớp: {int(g.auto_cancel_orders.sum())}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'data_14d.csv', sys.argv[2] if len(sys.argv) > 2 else 'data.json')
