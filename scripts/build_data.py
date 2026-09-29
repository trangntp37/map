"""Dựng data.json cho trang heatmap từ file export 14 ngày (data_14d.csv).
Chạy:  python build_data.py data_14d.csv data.json
       python fix_wards.py data.json          (bước sau, giữ nguyên như cũ)
Cần:   pip install pandas

Đầu ra giữ đúng định dạng trang đang đọc:
  F      = ["c","rg","w","st","b","sl","lat","lng","hx"]
  stores = 1 dòng / điểm lấy hàng (tỉnh + partner + lat + lng)
  cells  = [sid, giờ, thứ(1=T2..7=CN), tổng đơn, đơn bị bỏ lỡ]
Đơn bị bỏ lỡ = auto_cancel_orders (không tài xế nào nhận).
hx = hex_id của công ty, lấy nguyên từ file, không tự tính.
"""
import re, sys, json
import pandas as pd

# Tên vùng ngắn (cột rg), giữ như data cũ
RG = {'BDG': 'Bình Dương', 'DNI': 'Đồng Nai', 'DAD': 'Đà Nẵng', 'HPH': 'Hải Phòng', 'CXR': 'Nha Trang',
      'VCA': 'Cần Thơ', 'DLI': 'Đà Lạt', 'VII': 'Vinh', 'BMV': 'Buôn Ma Thuột', 'VCS': 'Vũng Tàu',
      'HUI': 'Huế', 'BNH': 'Bắc Ninh', 'LAN': 'Long An', 'PXU': 'Pleiku', 'THD': 'Thanh Hóa',
      'PHH': 'Phan Thiết', 'VDO': 'Vân Đồn', 'TGG': 'Tiền Giang'}
# Tên hiển thị partner (cột b); partner không có ở đây thì hiện nguyên mã
BRAND = {'sme': 'Khách lẻ (SME)', 'concung': 'Con Cưng', 'pharmacity': 'Pharmacity', 'longchau': 'Long Châu',
         'ahafoodai': 'AhaFood AI', 'dienmayxanh': 'Điện Máy Xanh', 'bachhoaxanh': 'Bách Hóa Xanh',
         'viettelpost': 'Viettel Post', 'aeonvn': 'AEON', 'abbott': 'Abbott', 'fpt': 'FPT Shop'}
HOUSE_NO = re.compile(r'^(số\s*)?[\w/.-]*\d[\w/.-]*\s+', re.I)
WARD_PREFIX = re.compile(r'^(phường|xã|thị trấn|đặc khu)\s+', re.I)


def street(addr):
    first = addr.split(',')[0].strip()
    return HOUSE_NO.sub('', first).strip() or first


def label(b, addr):
    parts = [p.strip() for p in addr.split(',') if p.strip()]
    return f"{b} – {', '.join(parts[:2])}"


def main(src, dst):
    df = pd.read_csv(src, dtype={'hex_id': str})
    days = df['order_date_vn'].nunique()
    key = ['city_id', 'partner', 'pickup_lat', 'pickup_lng']
    df['sid'] = df.groupby(key, sort=True).ngroup()

    # 1 cửa hàng = địa chỉ / phường / hex xuất hiện nhiều nhất tại điểm đó
    mode = lambda s: s.dropna().mode().iat[0] if s.notna().any() else None
    st = df.groupby('sid').agg(c=('city_id', 'first'), p=('partner', 'first'), lat=('pickup_lat', 'first'),
                               lng=('pickup_lng', 'first'), addr=('pickup_address', mode),
                               w=('pickup_ward', mode), hx=('hex_id', mode)).reset_index()
    stores = []
    for r in st.itertuples():
        b = BRAND.get(r.p, r.p)
        w = WARD_PREFIX.sub('', r.w).strip() if isinstance(r.w, str) else 'Không rõ'
        addr = r.addr or ''
        stores.append([r.c, RG.get(r.c, r.c), w, street(addr), b, label(b, addr),
                       round(float(r.lat), 4), round(float(r.lng), 4), r.hx])

    g = (df.groupby(['sid', 'order_hour', 'weekday_iso'])[['total_orders', 'auto_cancel_orders']]
           .sum().reset_index())
    cells = g.astype(int).values.tolist()

    out = {'F': ['c', 'rg', 'w', 'st', 'b', 'sl', 'lat', 'lng', 'hx'], 'stores': stores, 'cells': cells}
    json.dump(out, open(dst, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))

    # kiểm tra: tổng đơn và đơn bỏ lỡ phải khớp file gốc
    assert g.total_orders.sum() == df.total_orders.sum()
    assert g.auto_cancel_orders.sum() == df.auto_cancel_orders.sum()
    print(f'{days} ngày ({df.order_date_vn.min()} → {df.order_date_vn.max()}) · '
          f'{len(stores)} cửa hàng · {len(cells)} cell · {df.hex_id.nunique()} hex · '
          f'tổng đơn khớp: {int(g.total_orders.sum())} · bỏ lỡ khớp: {int(g.auto_cancel_orders.sum())}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'data_14d.csv', sys.argv[2] if len(sys.argv) > 2 else 'data.json')
