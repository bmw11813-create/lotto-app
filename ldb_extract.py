# -*- coding: utf-8 -*-
"""
브라우저 localStorage(LevelDB) 에서 로또 앱 데이터 복구 → recovered_backup.json

Chrome/Edge 의 Local Storage 는 LevelDB 로, 키 형식이 다음과 같다.
    _<origin>\\x00\\x01<키>      값의 첫 바이트 0x00=UTF-16LE, 0x01=UTF-8(Latin-1)
로또 앱은 `round:<회차>` 키에 JSON 문자열을 저장한다(index.html handleSaveAsRecord).

.ldb(SST) 와 .log(write-ahead log) 를 모두 직접 파싱한다. 원본은 열지 않고
사본만 읽으며, 브라우저가 켜져 있어 잠긴 경우에도 안전하다.

실행: python ldb_extract.py [사본폴더 ...]
"""
import glob, json, os, shutil, struct, sys, tempfile
import snappy

ORIGIN = "https://bmw11813-create.github.io"
OUT = "recovered_backup.json"

_LA = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
BROWSER_DIRS = [
    os.path.join(_LA, r"Google\Chrome\User Data\*\Local Storage\leveldb"),
    os.path.join(_LA, r"Microsoft\Edge\User Data\*\Local Storage\leveldb"),
]

# ── varint ────────────────────────────────────────────────────
def uvarint(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1
        r |= (c & 0x7F) << s
        if not (c & 0x80):
            return r, i
        s += 7

# ── SST(.ldb) ─────────────────────────────────────────────────
FOOTER = 48
MAGIC = 0xDB4775248B80FB57

def read_block(buf, off, size):
    raw = buf[off:off + size]
    ctype = buf[off + size]                       # 0=none 1=snappy
    if ctype == 1:
        return snappy.uncompress(raw)
    if ctype == 0:
        return raw
    return None                                   # zstd 등은 건너뜀

def block_entries(blk):
    """leveldb 블록의 (key, value) 나열"""
    if len(blk) < 4:
        return
    nrest = struct.unpack_from("<I", blk, len(blk) - 4)[0]
    end = len(blk) - 4 - nrest * 4
    i, key = 0, b""
    while i < end:
        try:
            shared, i = uvarint(blk, i)
            nonshared, i = uvarint(blk, i)
            vlen, i = uvarint(blk, i)
            key = key[:shared] + blk[i:i + nonshared]
            i += nonshared
            val = blk[i:i + vlen]
            i += vlen
            yield key, val
        except Exception:
            return

def read_sst(path):
    buf = open(path, "rb").read()
    if len(buf) < FOOTER:
        return
    if struct.unpack_from("<Q", buf, len(buf) - 8)[0] != MAGIC:
        return
    f = len(buf) - FOOTER
    _, f2 = uvarint(buf, f); _, f2 = uvarint(buf, f2)      # metaindex handle 건너뜀
    ioff, f3 = uvarint(buf, f2)
    isize, _ = uvarint(buf, f3)
    idx = read_block(buf, ioff, isize)
    if idx is None:
        return
    for _k, handle in block_entries(idx):
        try:
            off, j = uvarint(handle, 0)
            size, _ = uvarint(handle, j)
            blk = read_block(buf, off, size)
            if blk is None:
                continue
            for k, v in block_entries(blk):
                yield k, v
        except Exception:
            continue

# ── write-ahead log(.log) ─────────────────────────────────────
def read_log(path):
    buf = open(path, "rb").read()
    payload, pos = b"", 0
    while pos + 7 <= len(buf):
        blk_left = 32768 - (pos % 32768)
        if blk_left < 7:
            pos += blk_left
            continue
        ln = struct.unpack_from("<H", buf, pos + 4)[0]
        rt = buf[pos + 6]
        data = buf[pos + 7:pos + 7 + ln]
        pos += 7 + ln
        if rt in (1, 2):            # FULL, FIRST
            payload = data
        else:                       # MIDDLE, LAST
            payload += data
        if rt in (1, 4):            # FULL, LAST → 배치 완성
            for kv in parse_batch(payload):
                yield kv
            payload = b""

def parse_batch(b):
    if len(b) < 12:
        return
    n = struct.unpack_from("<I", b, 8)[0]
    i = 12
    for _ in range(n):
        if i >= len(b):
            return
        t = b[i]; i += 1
        try:
            klen, i = uvarint(b, i)
            key = b[i:i + klen]; i += klen
            if t == 1:                       # PUT
                vlen, i = uvarint(b, i)
                val = b[i:i + vlen]; i += vlen
                yield key, val
            else:                            # DELETE
                yield key, None
        except Exception:
            return

# ── Chrome Local Storage 해석 ─────────────────────────────────
def decode_val(v):
    if not v:
        return None
    tag, body = v[0], v[1:]
    try:
        if tag == 0:
            return body.decode("utf-16-le", "replace")
        if tag == 1:
            return body.decode("utf-8", "replace")
    except Exception:
        pass
    return v.decode("utf-8", "replace")

def scan(paths):
    found, deleted = {}, set()
    prefix = ("_" + ORIGIN).encode() + b"\x00\x01"
    for p in paths:
        for fn in sorted(glob.glob(os.path.join(p, "*"))):
            base = os.path.basename(fn).lower()
            try:
                it = read_sst(fn) if base.endswith(".ldb") else \
                     read_log(fn) if base.endswith(".log") else None
                if it is None:
                    continue
                for k, v in it:
                    kk = k[:-8] if base.endswith(".ldb") and len(k) > 8 else k  # SST 키는 8B 시퀀스 꼬리
                    if not kk.startswith(prefix):
                        continue
                    name = kk[len(prefix):].decode("utf-8", "replace")
                    if v is None:
                        deleted.add(name); continue
                    found[name] = decode_val(v)
            except Exception as e:
                print(f"  ! {fn}: {type(e).__name__}")
    return found, deleted

def main():
    if len(sys.argv) > 1:
        paths = sys.argv[1:]
    else:
        tmp = tempfile.mkdtemp(prefix="ls_")
        paths = []
        for pat in BROWSER_DIRS:
            for src in glob.glob(pat):
                dst = os.path.join(tmp, str(len(paths)))
                os.makedirs(dst, exist_ok=True)
                for f in glob.glob(os.path.join(src, "*")):
                    try:
                        shutil.copy2(f, dst)      # 잠겨 있어도 사본만 시도
                    except Exception:
                        pass
                paths.append(dst)
                print(f"사본: {src}")
    found, deleted = scan(paths)

    rounds, others = [], {}
    for k, v in sorted(found.items()):
        if k.startswith("round:"):
            try:
                rounds.append(json.loads(v))
            except Exception:
                print(f"  ! {k} JSON 파싱 실패")
        else:
            others[k] = v[:200] if isinstance(v, str) else v
    rounds.sort(key=lambda r: -r.get("round", 0))

    print(f"\n{ORIGIN} 키 {len(found)}개 발견 (삭제표시 {len(deleted)}개)")
    print(f"  round: 레코드 {len(rounds)}개")
    for k in others:
        print(f"  기타 키: {k} = {others[k]!r}")

    data = {"exportDate": "recovered-from-localstorage", "rounds": rounds}
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"저장 → {OUT}")
    return rounds


if __name__ == "__main__":
    rs = main()
    for r in rs:
        g = r.get("games") or []
        print(f"  {r.get('round')}회 {r.get('date','')} 게임 {len(g)}줄 "
              f"당첨번호={r.get('winNumbers')} 보너스={r.get('bonus')} "
              f"기록전용={r.get('recordOnly', False)}")
