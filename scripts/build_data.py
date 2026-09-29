"""Dựng data.json cho trang heatmap từ file export 14 ngày (data_14d.csv).
Chạy:  python build_data.py data_14d.csv data.json
       python fix_wards.py data.json          (bước sau, giữ nguyên như cũ)
Cần:   pip install pandas h3

Đầu ra giữ đúng định dạng trang đang đọc:
  F      = ["c","rg","w","st","b","sl","lat","lng","hx"]
  stores = 1 dòng / điểm lấy hàng (tỉnh + partner + lat + lng)
  cells  = [sid, giờ, thứ(1=T2..7=CN), tổng đơn, đơn bị bỏ lỡ]
Đơn bị bỏ lỡ = auto_cancel_orders (không tài xế nào nhận).
hx = mã H3 res 8 (~0,74 km²/ô) tính từ pickup_lat/lng. Cột hex_id trong CSV (nếu có) bỏ qua.
st = tên đường, đã bỏ số nhà / ngõ / mã cửa hàng; không nhận ra tên đường thì để trống.
"""
import re, sys, json
import pandas as pd
import h3

HEX_RES = 8

# Tên vùng ngắn (cột rg), giữ như data cũ
RG = {'BDG': 'Bình Dương', 'DNI': 'Đồng Nai', 'DAD': 'Đà Nẵng', 'HPH': 'Hải Phòng', 'CXR': 'Nha Trang',
      'VCA': 'Cần Thơ', 'DLI': 'Đà Lạt', 'VII': 'Vinh', 'BMV': 'Buôn Ma Thuột', 'VCS': 'Vũng Tàu',
      'HUI': 'Huế', 'BNH': 'Bắc Ninh', 'LAN': 'Long An', 'PXU': 'Pleiku', 'THD': 'Thanh Hóa',
      'PHH': 'Phan Thiết', 'VDO': 'Vân Đồn', 'TGG': 'Tiền Giang'}
# Tên hiển thị partner (cột b); partner không có ở đây thì hiện nguyên mã
BRAND = {'sme': 'Khách lẻ (SME)', 'concung': 'Con Cưng', 'pharmacity': 'Pharmacity', 'longchau': 'Long Châu',
         'ahafoodai': 'AhaFood AI', 'dienmayxanh': 'Điện Máy Xanh', 'bachhoaxanh': 'Bách Hóa Xanh',
         'viettelpost': 'Viettel Post', 'aeonvn': 'AEON', 'abbott': 'Abbott', 'fpt': 'FPT Shop'}
WARD_PREFIX = re.compile(r'^(phường|xã|thị trấn|đặc khu)\s+', re.I)


# ---- tách tên đường từ địa chỉ ----
ADMIN = re.compile(r'^(p\.|phường|phuong|xã|x\.|q\.|quận|huyện|h\.|tp\.?|t\.|thành phố|tỉnh|thị xã|tx\.|thị trấn|tt\.|kp\.?|khu phố|khu vực|kv\.?|ấp|tổ|việt nam|vietnam|vn)(\s|$|\.)', re.I)
PLUS = re.compile(r'^[23456789CFGHJMPQRVWX]{4,8}\+[23456789CFGHJMPQRVWX]{2,3}\b', re.I)
KEY = re.compile(r'^(đường|đ\.|phố|đại lộ|quốc lộ|ql\.?|tỉnh lộ|tl\.?|đt\.?|hương lộ)(\s|\d|$)', re.I)
# số nhà ở đầu: 278 / 26/38 / 11A / K13 / A8-38 / 92 - 94 / Số 8 / Lô 7C / Kiot 12 / Nhà LK-03 / Thửa số 701
HN = re.compile(r'^(số|so|lô|lo|kiot|ki ốt|nhà|căn|căn hộ|thửa( số)?|ô)?\s*([a-z]{0,3}\d+[a-z\d]*([/\-.][a-z\d]+)*)(\s*-\s*\d+[a-z\d]*)?(\s+|$)', re.I)
ALLEY = re.compile(r'^(hẻm|hẽm|ngõ|ngách|kiệt|kiet|hem|ngo)\s*\d+[a-z\d/]*\s+', re.I)
TAIL = re.compile(r'\s+((-|st\.?|street)(\s.*)?|(tầng|lầu|phòng|tòa|toà|block|kp\.?|khu phố|ấp|tổ|kdc|khu dân cư)[\s.].+)$', re.I)
SKIP = re.compile(r'^(tờ bản đồ|tờ bđ|thửa|lô đất)', re.I)
PHONE = re.compile(r'(?:\+84|\b0)\d{9}\b')
DUONG = re.compile(r'^(đường|đ\.)\s*(?=[^\d\s])(?!số\b)(?![a-zđ]\d)', re.I)

def street(addr):
    had_no = False
    for part in re.split(r',|\s\|\s', PHONE.sub('', addr or '')):
        p = re.sub(r'\S*_\S*\s*-?\s*|\([^)]*\)', ' ', part)   # bỏ mã cửa hàng (có dấu _) và phần trong ngoặc
        p = re.sub(r'\s+', ' ', p).strip(' .-')
        if not p or PLUS.match(p) or ADMIN.match(p) or re.fullmatch(r'\d{5,6}', p) or SKIP.match(p):
            continue
        stripped = False
        while True:
            m = HN.match(p)
            if not m or re.match(r'^\d+\s+tháng\b', p, re.I): break
            p = p[m.end():].strip(' .-,'); stripped = True
        p = ALLEY.sub('', p)
        if p and (ADMIN.match(p) or re.match(r'^khu\s*\d', p, re.I)):
            had_no = False; continue
        if not p:
            had_no = had_no or stripped; continue
        if stripped or had_no or KEY.match(p):
            p = TAIL.sub('', p).strip(' .-')
            p = DUONG.sub('', p).strip()
            if p and not re.fullmatch(r'[\d\W]+', p) and len(p) <= 40:
                return ' '.join(w[:1].upper() + w[1:] if w.islower() else w for w in p.split())
        had_no = False
    return ''


def label(b, addr):
    parts = [p.strip() for p in addr.split(',') if p.strip()]
    return f"{b} – {', '.join(parts[:2])}"


def main(src, dst):
    df = pd.read_csv(src)
    days = df['order_date_vn'].nunique()
    key = ['city_id', 'partner', 'pickup_lat', 'pickup_lng']
    df['sid'] = df.groupby(key, sort=True).ngroup()

    # 1 cửa hàng = địa chỉ / phường / hex xuất hiện nhiều nhất tại điểm đó
    mode = lambda s: s.dropna().mode().iat[0] if s.notna().any() else None
    st = df.groupby('sid').agg(c=('city_id', 'first'), p=('partner', 'first'), lat=('pickup_lat', 'first'),
                               lng=('pickup_lng', 'first'), addr=('pickup_address', mode),
                               w=('pickup_ward', mode)).reset_index()
    stores = []
    for r in st.itertuples():
        b = BRAND.get(r.p, r.p)
        w = WARD_PREFIX.sub('', r.w).strip() if isinstance(r.w, str) else 'Không rõ'
        addr = r.addr or ''
        stores.append([r.c, RG.get(r.c, r.c), w, street(addr), b, label(b, addr),
                       round(float(r.lat), 4), round(float(r.lng), 4),
                       h3.latlng_to_cell(float(r.lat), float(r.lng), HEX_RES)])

    g = (df.groupby(['sid', 'order_hour', 'weekday_iso'])[['total_orders', 'auto_cancel_orders']]
           .sum().reset_index())
    cells = g.astype(int).values.tolist()

    out = {'F': ['c', 'rg', 'w', 'st', 'b', 'sl', 'lat', 'lng', 'hx'], 'stores': stores, 'cells': cells}
    json.dump(out, open(dst, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))

    # kiểm tra: tổng đơn và đơn bỏ lỡ phải khớp file gốc
    assert g.total_orders.sum() == df.total_orders.sum()
    assert g.auto_cancel_orders.sum() == df.auto_cancel_orders.sum()
    print(f'{days} ngày ({df.order_date_vn.min()} → {df.order_date_vn.max()}) · '
          f'{len(stores)} cửa hàng · {len(cells)} cell · {len({s[8] for s in stores})} hex res {HEX_RES} · '
          f'tổng đơn khớp: {int(g.total_orders.sum())} · bỏ lỡ khớp: {int(g.auto_cancel_orders.sum())}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'data_14d.csv', sys.argv[2] if len(sys.argv) > 2 else 'data.json')
