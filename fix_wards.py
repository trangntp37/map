"""Vá cột phường "Không rõ" trong data.json.
Chạy:  python scripts/fix_wards.py data.json   (ghi đè tại chỗ)
Cần:   pip install numpy scikit-learn

B1. Học bảng tên phường cũ -> mới từ chính dữ liệu: địa chỉ gốc ghi tên phường cũ
    (trước sáp nhập 7/2025) còn cột phường ghi tên mới. Chỉ giữ cặp xuất hiện >=3 lần
    và >=80% trỏ về cùng 1 phường mới.
B2. Chuẩn hoá nhãn cũ đang lẫn trong dữ liệu (vd "Thạc Gián" -> "Thanh Khê").
B3. Cửa hàng "Không rõ": lấy tên phường ở cuối địa chỉ / sau plus-code, tra bảng B1.
B4. Còn lại: lấy phường chiếm >=70% trong 9 cửa hàng gần nhất cùng tỉnh, bán kính 1 km.
"""
import json, re, sys, unicodedata, collections as C
import numpy as np
from sklearn.neighbors import BallTree

UNK = 'Không rõ'; R = 6371000.0
PC = re.compile(r'^[23456789CFGHJMPQRVWX]{4}\+[23456789CFGHJMPQRVWX]{2,3}\s+(.+)$')

def norm(x):
    x = unicodedata.normalize('NFD', x.lower()).replace('đ', 'd')
    x = ''.join(ch for ch in x if unicodedata.category(ch) != 'Mn')
    x = re.sub(r'^(phuong|p\.|xa|x\.|thi tran|tt\.|quan|huyen|thanh pho|tp\.?|thi xa|tx\.)\s*', '', x.strip())
    return re.sub(r'\s+', ' ', x).strip(' .,')

def main(path):
    d = json.load(open(path, encoding='utf-8'))
    F = d['F']; S = d['stores']
    IC, IW, IST, ISL, ILAT, ILNG = (F.index(k) for k in ('c', 'w', 'st', 'sl', 'lat', 'lng'))

    def tokens(r):
        out = []
        parts = [x.strip() for x in r[ISL].split('–', 1)[-1].split(',')]
        if len(parts) > 1: out.append(norm(parts[-1]))
        m = PC.match(r[IST] or '')
        if m: out.append(norm(m.group(1)))
        return [t for t in out if t and t not in ('vietnam', 'viet nam')]

    # B1
    tab = C.defaultdict(C.Counter)
    for r in S:
        if r[IW] != UNK:
            for t in tokens(r): tab[(r[IC], t)][r[IW]] += 1
    MAP = {}
    for k, c in tab.items():
        lab, n = c.most_common(1)[0]; tot = sum(c.values())
        if tot >= 3 and n / tot >= 0.8: MAP[k] = lab
    # B2
    W = []
    for r in S:
        y = MAP.get((r[IC], norm(r[IW]))) if r[IW] != UNK else None
        W.append(y if y else r[IW])
    # B3
    for i, r in enumerate(S):
        if W[i] == UNK:
            g = next((MAP[(r[IC], t)] for t in tokens(r) if (r[IC], t) in MAP), None)
            if g: W[i] = g
    # B4
    by = C.defaultdict(list)
    for i, r in enumerate(S):
        if W[i] != UNK: by[r[IC]].append(i)
    trees = {p: BallTree(np.radians([[S[i][ILAT], S[i][ILNG]] for i in L]), metric='haversine')
             for p, L in by.items()}
    for q, r in enumerate(S):
        if W[q] != UNK or r[IC] not in trees: continue
        L = by[r[IC]]
        dist, idx = trees[r[IC]].query(np.radians([[r[ILAT], r[ILNG]]]), k=min(9, len(L)))
        nb = [W[L[j]] for dd, j in zip(dist[0], idx[0]) if dd * R <= 1000]
        if len(nb) < 2: continue
        lab, c = C.Counter(nb).most_common(1)[0]
        if c / len(nb) >= 0.7: W[q] = lab

    before = sum(r[IW] == UNK for r in S)
    for i, r in enumerate(S): r[IW] = W[i]
    print(f'Không rõ: {before} -> {sum(w == UNK for w in W)} / {len(S)} cửa hàng')
    json.dump(d, open(path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'data.json')
