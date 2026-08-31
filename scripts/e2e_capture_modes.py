"""3모드 촬영 계약 e2e — SDK 제안서 §5 '완료 확인 시퀀스' + 방어 케이스.

사용: BASE_URL/E2E_EMAIL/E2E_PASSWORD 환경변수 (기본 localhost:8738, admin 계정 전제).
주의: ctg/ref/세션/캡처 데이터를 생성하므로 운영 DB에서는 실행하지 말 것. 재실행 안전.
"""
import io
import os
import time
import requests, json, sys

B = os.environ.get("BASE_URL", "http://localhost:8738")
EMAIL = os.environ.get("E2E_EMAIL", "e2e@test.com")
PW = os.environ.get("E2E_PASSWORD", "pw123456!")
ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    mark = "✅" if cond else "❌"
    if cond: ok += 1
    else: fail += 1
    print(f"{mark} {name}{' — ' + str(extra) if extra and not cond else ''}")

T_RUN = int(time.time()) - 2
T_MS = int(time.time() * 1000)

# 0. 로그인 (admin + client)
requests.post(f"{B}/api/auth/signup", json={"name":"e2e유저","email":EMAIL,"password":PW,"passwordCheck":PW,"nickname":"e2e"})
r = requests.post(f"{B}/api/auth/login", json={"email":EMAIL,"password":PW})
H = {"Authorization": f"Bearer {r.json()['data']['accessToken']}"}
requests.post(f"{B}/api/auth/signup", json={"name":"e2e클라","email":"e2e-client@test.com","password":PW,"passwordCheck":PW,"nickname":"e2ec"})
rc = requests.post(f"{B}/api/auth/login", json={"email":"e2e-client@test.com","password":PW})
HC = {"Authorization": f"Bearer {rc.json()['data']['accessToken']}"}
check("0. login (admin+client)", r.status_code==200 and rc.status_code==200)

# ref 확보
r = requests.post(f"{B}/api/ctg/create", json={"userId":1,"name":f"e2e3모드-{T_RUN}"}, headers=H)
if r.status_code == 403:
    print(f"❌ ADMIN 권한 필요: UPDATE tb_user SET role='ADMIN' WHERE email='{EMAIL}';"); sys.exit(1)
ctg = r.json()["data"]["id"]
img = requests.post(f"{B}/api/ref/create", json={"ctgId":ctg,"imgUrl":"reference/e2e3.png","title":"3모드 ref"}, headers=H).json()["data"]["imgId"]

# ── §5 완료 시퀀스: 세션 모드 3종 ──
# 1. mode 미전송 → fashion_ref (하위호환)
r = requests.post(f"{B}/api/session/start", json={"imgId":img,"device":{"platform":"iOS"}}, headers=H)
d = r.json()["data"]
check("1. mode 미전송 → fashion_ref 저장", r.status_code==200 and d["mode"]=="fashion_ref" and d["imgId"]==img, r.text[:150])
sid_fashion = d["id"]

# 2. aesthetic_ref: imgId 있으면 200, 없으면 422
r = requests.post(f"{B}/api/session/start", json={"imgId":img,"mode":"aesthetic_ref"}, headers=H)
d = r.json()["data"]
check("2a. aesthetic_ref + imgId → 200", r.status_code==200 and d["mode"]=="aesthetic_ref")
sid_aes = d["id"]
r = requests.post(f"{B}/api/session/start", json={"mode":"aesthetic_ref"}, headers=H)
check("2b. aesthetic_ref imgId 누락 → 422", r.status_code==422, r.text[:150])

# 3. direct: imgId 없이 200, imgId 보내도 무시(null)
r = requests.post(f"{B}/api/session/start", json={"mode":"direct","device":{"platform":"iOS"}}, headers=H)
d = r.json()["data"]
check("3a. direct imgId 없이 → 200 + imgId null", r.status_code==200 and d["mode"]=="direct" and d["imgId"] is None, r.text[:150])
sid_direct = d["id"]
r = requests.post(f"{B}/api/session/start", json={"mode":"direct","imgId":img}, headers=H)
check("3b. direct + imgId → 무시(null 저장)", r.json()["data"]["imgId"] is None)

# 4. 과도기: device.mode 승격
r = requests.post(f"{B}/api/session/start", json={"device":{"platform":"iOS","mode":"direct"}}, headers=H)
check("4. device.mode=direct 승격", r.status_code==200 and r.json()["data"]["mode"]=="direct")

# 5. session/list filter mode
def slist(flt):
    return requests.post(f"{B}/api/session/list", json={"page":1,"limit":50,"filter":{**flt,"sDate":T_RUN}}, headers=H).json()["data"]
check("5. list filter mode=direct", slist({"mode":"direct"})["total"]==3 and slist({"mode":"aesthetic_ref"})["total"]==1,
      json.dumps({m: slist({"mode":m})["total"] for m in ("fashion_ref","aesthetic_ref","direct")}))

# 6. files type=capture 업로드
png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
r = requests.post(f"{B}/api/files/create", files={"file": ("cap.png", io.BytesIO(png), "image/png")},
                  data={"type": "capture"}, headers=H)
if r.status_code == 201:
    cap_url = r.json()["data"]["url"]
    check("6. files/create type=capture", "captures/" in r.json()["data"]["fileKey"], r.text[:200])
elif r.status_code >= 500:
    # 로컬에 S3 자격증명이 없으면 업로드는 실패한다 — capture 계약 자체는 URL 문자열만
    # 소비하므로 검증에 지장 없음. 실서버 검증 시에는 이 스킵이 나오면 안 된다.
    cap_url = None
    print("⚠️  6. files/create type=capture — 스토리지 자격증명 없음으로 스킵 (로컬 한정 허용)")
else:
    cap_url = None
    check("6. files/create type=capture", False, r.text[:200])

# 7. 같은 direct 세션에 direct 1장 + ai_director 1장 (계약 §5 경계 케이스)
mk = lambda mode, **kw: {"sId":sid_direct,"mode":mode,"captureUrl":cap_url or "captures/x.png","capturedAt":T_MS,**kw}
r1 = requests.post(f"{B}/api/capture/create", json=mk("direct"), headers=H)
r2 = requests.post(f"{B}/api/capture/create", json=mk("ai_director", analysis={"score":0.91,"axis":"pitch"}), headers=H)
check("7. direct 세션에 direct+ai_director 2건", r1.status_code==200 and r2.status_code==200
      and r1.json()["status"]["code"]=="S0001", (r1.text+r2.text)[:200])
cap_ai = r2.json()["data"]["id"]

# 8. aesthetic_ref 캡처 (imgId 연결, 세션 없이도 등록 가능 — sId 옵션)
r = requests.post(f"{B}/api/capture/create", json={"mode":"aesthetic_ref","imgId":img,"captureUrl":cap_url or "captures/x.png","capturedAt":T_MS}, headers=H)
check("8. aesthetic_ref 캡처 (sId 없이) → 200", r.status_code==200)

# 9. capture/list — mode 필터 + 정렬
def clist(flt, headers=H):
    return requests.post(f"{B}/api/capture/list", json={"page":1,"limit":50,"filter":{**flt,"fromDate":T_MS-1000}}, headers=headers).json()["data"]
check("9a. capture/list filter mode=ai_director", clist({"mode":"ai_director"})["total"]==1)
check("9b. capture/list filter sId", clist({"sId":sid_direct})["total"]==2)
check("9c. analysis 왕복", clist({"mode":"ai_director"})["items"][0]["analysis"]["score"]==0.91)

# 10. 권한 — 사적 촬영물 모델
check("10a. 비-admin list는 본인 것만", clist({}, headers=HC)["total"]==0)
r = requests.post(f"{B}/api/capture/get", json={"id":cap_ai}, headers=HC)
check("10b. 타인 capture/get → 403", r.status_code==403)
r = requests.post(f"{B}/api/capture/create", json=mk("direct"), headers=HC)
check("10c. 타인 세션 연결 → 403", r.status_code==403)
r = requests.post(f"{B}/api/capture/delete", json={"id":cap_ai}, headers=HC)
check("10d. delete는 admin 전용 → 403", r.status_code==403)

# 11. 방어 케이스 (리뷰 교훈: DB가 못 받는 값은 500 대신 422)
r = requests.post(f"{B}/api/capture/create", json=mk("m"*17), headers=H)
check("11a. mode 17자 → 422", r.status_code==422)
r = requests.post(f"{B}/api/capture/create", json=mk("direct", captureUrl="u"*501), headers=H)
check("11b. captureUrl 501자 → 422", r.status_code==422)
body = json.dumps(mk("direct", analysis={"x": float("nan")}), ensure_ascii=False)
r = requests.post(f"{B}/api/capture/create", data=body.encode(), headers={**H,"Content-Type":"application/json"})
check("11c. analysis NaN → 200 (소독)", r.status_code==200, r.text[:150])
r = requests.post(f"{B}/api/capture/create", json=mk("direct", capturedAt=9223372036854775808), headers=H)
check("11d. capturedAt BIGINT 초과 → 422", r.status_code==422)
r = requests.post(f"{B}/api/capture/create", json={**mk("direct"), "sId":"없는세션없는세션없는세션없는세션없는세션없"[:32]}, headers=H)
check("11e. 미존재 sId → 400", r.status_code==400)

# 12. 기존 플로우 회귀 없음 — fashion_ref 세션은 텔레메트리·end 정상
r = requests.post(f"{B}/api/system/send", json={"sId":sid_fashion,"secSeq":1,"payload":[{"fseq":0,"tid":T_MS,"offsetMs":0,"gate":5}]}, headers=H)
check("12a. fashion_ref 세션 텔레메트리 정상", r.status_code==200)
r = requests.post(f"{B}/api/session/end", json={"id":sid_fashion}, headers=H)
check("12b. end + mode 포함 응답", r.json()["data"]["mode"]=="fashion_ref" and r.json()["data"]["snapshotFlush"]["persistedSecs"]==1)

# 13. admin delete
r = requests.post(f"{B}/api/capture/delete", json={"id":cap_ai}, headers=H)
check("13. admin delete → 200", r.status_code==200)

print(f"\n결과: {ok} 통과 / {fail} 실패")
sys.exit(1 if fail else 0)
