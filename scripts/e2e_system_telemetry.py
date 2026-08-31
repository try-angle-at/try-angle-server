"""system 텔레메트리 e2e 검증 — SDK 복원요청 문서의 '완료 확인 시퀀스' 자동화.

사용: BASE_URL/E2E_EMAIL/E2E_PASSWORD 환경변수로 대상 서버 지정 (기본 localhost:8738).
전제: E2E_EMAIL 계정이 ADMIN 권한(ctg/ref 생성용). 없으면 가입 후
  UPDATE tb_user SET role='ADMIN' WHERE email='<E2E_EMAIL>';
를 수동 실행해야 한다 (권한 부족 시 스크립트가 안내 후 종료).
주의: ctg/ref/세션 데이터를 생성하므로 운영 DB에서는 실행하지 말 것.
재실행 안전: 목록 필터 검증은 이번 실행 시작 시각(sDate)으로 스코핑한다.
"""
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

T_RUN = int(time.time()) - 2  # 이번 실행 세션만 목록 필터에 걸리게 하는 스코프

# 1. 회원가입 + 로그인 (admin 계정)
requests.post(f"{B}/api/auth/signup", json={"name":"e2e유저","email":EMAIL,"password":PW,"passwordCheck":PW,"nickname":"e2e"})
r = requests.post(f"{B}/api/auth/login", json={"email":EMAIL,"password":PW})
tok = r.json()["data"]["accessToken"]; H = {"Authorization": f"Bearer {tok}"}
check("1. login", r.status_code==200)

# 별도 CLIENT 계정 (소유권/스코핑 검증용)
c_email = f"e2e-client@test.com"
requests.post(f"{B}/api/auth/signup", json={"name":"e2e클라","email":c_email,"password":PW,"passwordCheck":PW,"nickname":"e2ec"})
rc = requests.post(f"{B}/api/auth/login", json={"email":c_email,"password":PW})
HC = {"Authorization": f"Bearer {rc.json()['data']['accessToken']}"}

# 2. ctg + ref 생성 (admin 필요 — 아니면 안내 후 종료)
r = requests.post(f"{B}/api/ctg/create", json={"userId":1,"name":f"e2e전신-{T_RUN}"}, headers=H)
if r.status_code == 403:
    print(f"❌ ADMIN 권한 필요. 수동 실행: UPDATE tb_user SET role='ADMIN' WHERE email='{EMAIL}';")
    sys.exit(1)
ctg = r.json()["data"]["id"]
r = requests.post(f"{B}/api/ref/create", json={"ctgId":ctg,"imgUrl":"reference/e2e.png","title":"e2e ref"}, headers=H)
img = r.json()["data"]["imgId"]
check("2. ctg+ref 생성", bool(img))

# 3. session/start
r = requests.post(f"{B}/api/session/start", json={"imgId":img,"device":{"platform":"iOS","appVersion":"e2e"}}, headers=H)
sid = r.json()["data"]["id"]
check("3. session/start", r.status_code==200 and r.json()["status"]["code"]=="S0001" and len(sid)==32, r.text[:120])

# 4. system/send secSeq=1 — gate 6·8 포함 (le=5 제약 금지 증명) + extra 키 보존 검증용 conf
t0 = 1777986265000
def frame(fseq, off, gate, phase, cat, fb, stuck, cc, cur=None, **extra):
    f = {"fseq":fseq,"tid":t0+off,"offsetMs":off,"phase":phase,"pidx":gate,"gate":gate,
         "cur":cur or {"pitchDeg":-16.1},
         "res":{"score":0.49,"passed":cc,"feedback":fb,"category":cat,
                "metadata":{"axis":cat,"stuckSec":stuck,"canCapture":cc}}}
    f.update(extra)
    return f
b1 = {"sId":sid,"secSeq":1,"payload":[
    frame(0,0,3,"CAMERA_ADJUST","pitch","휴대폰 위쪽을 뒤로 기울여주세요",3.2,False, conf=0.93),
    frame(1,33,6,"POSE_MATCH","pose","오른팔을 내려주세요",1.0,False,{"kp":"16140d32"}),
    frame(2,66,8,"FINALIZE","pose","좋아요, 유지하세요",0.0,True),
]}
r = requests.post(f"{B}/api/system/send", json=b1, headers=H)
check("4. system/send secSeq=1 (gate 6·8 포함)", r.status_code==200 and r.json()["data"]["frameCount"]==3, r.text[:200])

# 5. secSeq=2 — 다른 category/feedback (필터 테스트용) + canCapture 숫자 1 표현
b2 = {"sId":sid,"secSeq":2,"payload":[
    frame(3,0,2,"DISTANCE","distance","50cm 앞으로 다가가세요",5.5,False),
    frame(4,33,2,"DISTANCE","distance","거리 완벽",0.0,1),   # canCapture=1 → true로 인정돼야 함
]}
r = requests.post(f"{B}/api/system/send", json=b2, headers=H)
check("5. system/send secSeq=2 (canCapture=1 표현)", r.status_code==200)

# 6. secSeq=1 재전송 → 멱등 (409/500 아님)
r = requests.post(f"{B}/api/system/send", json=b1, headers=H)
check("6. 같은 배치 재전송 멱등", r.status_code==200, r.text[:120])

# 7. flushSec / flushSession
r = requests.post(f"{B}/api/system/flushSec", json={"sId":sid,"secSeq":1}, headers=H)
check("7a. flushSec", r.status_code==200 and r.json()["data"]["persisted"] is True)
r = requests.post(f"{B}/api/system/flushSession", json={"sId":sid}, headers=H)
check("7b. flushSession", r.status_code==200 and r.json()["data"]["persistedSecs"]==2)

# 8. session/detail → 평탄화 스냅샷 + extra 키 보존 + truncated
r = requests.post(f"{B}/api/session/detail", json={"id":sid}, headers=H)
d = r.json()["data"]
snaps = d["snapshots"]
check("8. detail snapshots 평탄화", d["secCount"]==2 and d["recordCount"]==5 and len(snaps)==5 and d["truncated"] is False,
      f"secCount={d.get('secCount')} recordCount={d.get('recordCount')}")
check("8a. 프레임 필드 보존 (gate=8, phase)", snaps[2]["gate"]==8 and snaps[2]["phase"]=="FINALIZE" and snaps[0]["cur"]["pitchDeg"]==-16.1)
check("8b. extra 키 왕복 보존 (conf)", snaps[0].get("conf")==0.93, json.dumps(snaps[0], ensure_ascii=False)[:150])

# 9. detail secSeq 범위 필터
r = requests.post(f"{B}/api/session/detail", json={"id":sid,"fromSecSeq":2}, headers=H)
d = r.json()["data"]
check("9. detail fromSecSeq=2", d["secCount"]==1 and d["recordCount"]==2)

# 10. session/list 집계 (이번 실행 세션만 — sDate 스코프)
def listhit(flt, headers=H):
    flt = {**flt, "sDate": T_RUN}
    r = requests.post(f"{B}/api/session/list", json={"page":1,"limit":10,"filter":flt}, headers=headers)
    return r.json()["data"]
lst = listhit({})
item = lst["items"][0]
check("10. list 집계", item["snapshotCount"]==2 and abs(item["maxStuckSec"]-5.5)<0.01 and item["mainFeedback"]=="거리 완벽",
      json.dumps({k:item.get(k) for k in ("snapshotCount","maxStuckSec","mainFeedback")}, ensure_ascii=False))

# 11. 스냅샷 필터
check("11a. filter feedback 부분일치", listhit({"feedback":"좋아요"})["total"]==1)
check("11b. filter category", listhit({"category":"distance"})["total"]==1 and listhit({"category":"없는값"})["total"]==0)
check("11c. filter stuckSec 실수 허용(5.4)", listhit({"stuckSec":5.4})["total"]==1 and listhit({"stuckSec":6})["total"]==0)
check("11d. filter canCapture=true (숫자1 인정 포함)", listhit({"canCapture":True})["total"]==1)
r = requests.post(f"{B}/api/session/list", json={"page":1,"limit":10,"feedback":"좋아요","sDate":T_RUN}, headers=H)
check("11e. flat body 하위호환", r.json()["data"]["total"]==1)

# 12. 소유권/스코핑
r = requests.post(f"{B}/api/system/send", json=b1, headers=HC)
check("12a. 타인 세션 send → 403", r.status_code==403, r.text[:120])
r = requests.post(f"{B}/api/system/flushSession", json={"sId":sid}, headers=HC)
check("12b. 타인 세션 flush → 403", r.status_code==403)
lc = listhit({}, headers=HC)
check("12c. 비-admin list는 본인 세션만", lc["total"]==0, json.dumps(lc)[:120])

# 13. 수신부 견고성 (전부 배치 유실 없이 처리돼야 함)
long_fb = "긴피드백" * 200  # 800자 > VARCHAR(500)
r = requests.post(f"{B}/api/system/send", json={"sId":sid,"secSeq":3,"payload":[frame(6,0,5,"P","cat_"+"x"*100,long_fb,1.0,True)]}, headers=H)
check("13a. 초장문 feedback/category → 200 (잘라서 저장)", r.status_code==200, r.text[:200])
r = requests.post(f"{B}/api/system/send", json={"sId":sid,"secSeq":4,"payload":[{**frame(7,0,5,"P","pose","ok",1.0,True), "res":{"feedback":"m","metadata":"n/a"}}]}, headers=H)
check("13b. metadata 비-dict → 200", r.status_code==200, r.text[:200])
# requests의 json=은 NaN을 거부하므로, 결함 클라이언트처럼 bare NaN 토큰을 raw로 전송
nan_frame = {**frame(8,0,5,"P","pose","ok",1.0,True)}; nan_frame["cur"] = {"x": float("nan")}
nan_body = json.dumps({"sId":sid,"secSeq":5,"payload":[nan_frame]}, ensure_ascii=False)  # allow_nan 기본 True → NaN 토큰 방출
r = requests.post(f"{B}/api/system/send", data=nan_body.encode(), headers={**H, "Content-Type":"application/json"})
check("13c. NaN 본문 → 200 (null 치환 저장)", r.status_code==200, r.text[:200])
r = requests.post(f"{B}/api/system/send", json={"sId":sid,"secSeq":2147483648,"payload":[frame(9,0,5,"P","pose","ok",1.0,True)]}, headers=H)
check("13d. secSeq INT 초과 → 422", r.status_code==422)
r = requests.post(f"{B}/api/system/send", json={"sId":sid,"secSeq":6,"payload":[]}, headers=H)
check("13e. 빈 payload → 422 (기존 배치 보호)", r.status_code==422)

# 14. session/end → snapshotFlush (13에서 3·4·5초 추가돼 5개)
r = requests.post(f"{B}/api/session/end", json={"id":sid}, headers=H)
d = r.json()["data"]
check("14. end + snapshotFlush", d["sStat"]==1 and d["snapshotFlush"]["persistedSecs"]==5, r.text[:200])

# 15. 경계 케이스
r = requests.post(f"{B}/api/system/send", json={**b1,"sId":"없는세션ID없는세션ID없는세션ID없는세션"}, headers=H)
check("15a. 미존재 sId → 404", r.status_code==404)
bad = {"sId":sid,"secSeq":7,"payload":[{**b1["payload"][0],"tid":t0+0.5}]}
r = requests.post(f"{B}/api/system/send", json=bad, headers=H)
check("15b. tid 소수 → 422", r.status_code==422)
r = requests.post(f"{B}/api/system/send", json=b1)
check("15c. 무인증 → 401", r.status_code==401)

print(f"\n결과: {ok} 통과 / {fail} 실패")
sys.exit(1 if fail else 0)
