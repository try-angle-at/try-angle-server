# TryAngle API 명세서

> **작성 기준:** 실제 소스코드(`src/service/*/**_api.py`, `**_schema.py`)에서 역추출
> **대상:** 프론트엔드/앱 개발자
> **문서 버전:** 2026-08-07

---

## 목차

1. [기본 규칙](#1-기본-규칙)
2. [인증](#2-인증)
3. [공통 응답 포맷](#3-공통-응답-포맷)
4. [에러 처리](#4-에러-처리)
5. [페이지네이션](#5-페이지네이션)
6. [엔드포인트](#6-엔드포인트)
   - [6.1 Basic](#61-basic)
   - [6.2 Auth](#62-auth-apiauth)
   - [6.3 Files](#63-files-apifiles)
   - [6.4 Category](#64-category-apictg)
   - [6.5 Reference](#65-reference-apiref)
   - [6.6 Product](#66-product-apiprod)
   - [6.7 Session](#67-session-apisession)
   - [6.8 Snap](#68-snap-apisnap)
7. [Enum / 상수 레퍼런스](#7-enum--상수-레퍼런스)
8. [전체 플로우 예제](#8-전체-플로우-예제)
9. [알려진 이슈](#9-알려진-이슈-반드시-확인)

---

## 1. 기본 규칙

| 항목 | 내용 |
|---|---|
| Base URL | `http://{host}:8738` (로컬 기본값) |
| Content-Type | `application/json` (파일 업로드만 `multipart/form-data`) |
| HTTP 메서드 | **조회 포함 거의 전부 `POST`.** `GET`은 `/api/health`, `/api/auth/me` 두 개뿐 |
| 식별자 전달 | 쿼리스트링 미사용. **모든 ID는 Request Body로** |
| 시간 형식 | **Unix Timestamp (초 단위, BigInt)**. 밀리초 아님 |
| 문자 인코딩 | UTF-8 |

> ⚠️ **`GET`이 아니라 `POST`입니다.** 목록 조회·상세 조회도 전부 POST + Body입니다.
> 캐싱이 필요하면 클라이언트 레벨에서 직접 처리해야 합니다.

---

## 2. 인증

### 방식

JWT Bearer 토큰. `POST /api/auth/login`으로 발급받아 이후 모든 요청 헤더에 실어 보냅니다.

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 토큰 정보

| 항목 | 값 |
|---|---|
| 알고리즘 | `HS256` |
| payload | `{"sub": "<email>", "role": "<UserRole>", "exp": <timestamp>}` |
| 유효기간 | 설정값 `access_token_expire_minutes` (기본 **1440분 = 24시간**) |
| 갱신 | **리프레시 토큰 없음.** 만료 시 재로그인 필요 |

### 권한 레벨

| 레벨 | 의미 | 적용 엔드포인트 |
|---|---|---|
| — | 토큰 불필요 | `/api/health`, `/api/auth/signup`, `/api/auth/login`, `/api/auth/exists`, `/api/auth/checkEmail` |
| **User** | 로그인만 하면 됨 | 위 목록 외 대부분 |
| **Admin** | `role`이 `ADMIN` 또는 `SUPER_ADMIN` | `/api/prod/create·update·delete`, `/api/snap/update·delete` |

### 인증 실패 응답

| 상황 | HTTP | 응답 |
|---|---|---|
| 헤더 없음 | 401 | `{"detail": "Not authenticated"}` |
| 토큰 만료/위조 | 401 | `{"detail": "Could not validate credentials"}` |
| 탈퇴/비활성 계정 | 401 | `{"detail": "User not found or inactive"}` |
| Admin 권한 부족 | 403 | `{"detail": "Admin privilege required"}` |

> ⚠️ **Swagger UI의 Authorize 버튼은 동작하지 않습니다.** `OAuth2PasswordBearer`의
> `tokenUrl`이 `/api/auth/token`으로 잡혀 있는데 그 엔드포인트가 존재하지 않습니다.
> 테스트 시 헤더를 직접 넣어주세요.

---

## 3. 공통 응답 포맷

성공 응답은 항상 아래 3-key 구조입니다.

```json
{
  "tid": 1705298638704,
  "status": {
    "code": "S0000",
    "msg": "성공"
  },
  "data": { }
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `tid` | int | 서버 응답 생성 시각 (**밀리초** Unix Timestamp). 로그 추적용 |
| `status.code` | string | 자체 상태 코드 (아래 표) |
| `status.msg` | string | 한국어 메시지 |
| `data` | object | 실제 페이로드. 없으면 `{}` |

> **`tid`만 밀리초입니다.** `data` 안의 `cDate`/`uDate`/`sDate` 등은 전부 초 단위입니다.

### 상태 코드

| code | HTTP | msg |
|---|---|---|
| `S0000` | 200 | 성공 |
| `S0001` | 201 | 리소스가 생성되었습니다 |
| `S0002` | 202 | 요청이 접수되었습니다 |
| `E0001` | 400 | 잘못된 요청입니다 |
| `E0002` | 401 | 인증이 필요합니다 |
| `E0003` | 403 | 접근이 거부되었습니다 |
| `E0004` | 404 | 리소스를 찾을 수 없습니다 |
| `E0006` | 409 | 이미 존재하는 리소스입니다 |
| `E0008` | 413 | 요청 데이터가 너무 큽니다 |
| `E0010` | 422 | 유효성 검사에 실패했습니다 |
| `E0500` | 500 | 서버 내부 오류가 발생했습니다 |

---

## 4. 에러 처리

### ⚠️ 에러 응답은 공통 포맷이 **아닙니다**

전역 예외 핸들러가 등록되어 있지 않아, 에러는 FastAPI 기본 형식으로 내려갑니다.

```json
// 성공 — 3-key 구조
{ "tid": 1705298638704, "status": { "code": "S0000", "msg": "성공" }, "data": {...} }

// 에러 — detail 하나뿐
{ "detail": "Session not found" }
```

**클라이언트는 두 형태를 모두 처리해야 합니다.** 권장 분기 방식:

```ts
// HTTP status로 판단하는 것이 가장 안전합니다
if (res.status >= 400) {
  const { detail } = await res.json();   // 에러
} else {
  const { tid, status, data } = await res.json();  // 성공
}
```

### 유효성 검사 실패 (422)

Pydantic 검증 실패 시 FastAPI 표준 형식입니다.

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "imgId"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

---

## 5. 페이지네이션

목록 조회는 공통적으로 아래 요청/응답 구조를 씁니다.

**요청**
```json
{ "page": 1, "limit": 20, "filter": { } }
```

**응답 `data`**
```json
{ "items": [ ], "total": 137, "page": 1, "limit": 20 }
```

| 필드 | 기본값 | 제약 |
|---|---|---|
| `page` | `1` | 1부터 시작 |
| `limit` | `20` | `1 ~ 100` |
| `total` | — | 필터 적용된 전체 건수 |

### ⚠️ `page: 0` 지원 여부가 엔드포인트마다 다릅니다

| 엔드포인트 | `page: 0` | 동작 |
|---|:-:|---|
| `/api/ref/list` | ✅ | **전체 조회** (LIMIT 없이 전부 반환) |
| `/api/ctg/list` | ✅ | **전체 조회** |
| `/api/prod/list` | ❌ | 422 에러 (`ge=1`) |
| `/api/snap/list` | ❌ | 422 에러 (`ge=1`) |
| `/api/session/list` | ❌ | 422 에러 (`ge=1`) |

---

## 6. 엔드포인트

### 6.1 Basic

#### `GET /api/health`

헬스체크. 인증 불필요.

**응답 (200)** — ⚠️ **공통 포맷이 아닙니다**

```json
{
  "tid": "20260807-143022-a3f8b2",
  "status": "pong",
  "message": "Hello from basic_service"
}
```

> `status`가 객체가 아니라 문자열이고, `tid`도 숫자가 아니라 문자열입니다.
> 이 엔드포인트만 별도 형식이니 파서를 공유하지 마세요.

---

### 6.2 Auth (`/api/auth`)

#### `POST /api/auth/signup` — 회원가입

**인증** 불필요 · **HTTP 201**

**Request Body**

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|---|---|:-:|---|---|
| `name` | string | ✅ | — | 실명 |
| `email` | string(email) | ✅ | — | 로그인 이메일. 형식 검증됨 |
| `password` | string | ⚠️ | `null` | 이메일 가입 시 필수, 소셜 가입 시 생략 |
| `passwordCheck` | string | — | `null` | 있으면 `password`와 일치 검사 |
| `nickname` | string | — | `null` | 서비스 내 표시명 |
| `phone` | string | — | `null` | 연락처 |
| `emailConf` | string | — | `"2"` | `"1"`=인증완료, `"2"`=미인증 |
| `desc` | string | — | `null` | 자기소개 |
| `filePath` | string | — | `null` | 프로필 이미지 경로 (DB `fileId` 컬럼에 저장) |
| `extra` | object | — | `{}` | 부가 정보 |
| `provider` | string | — | `"email"` | `email` / `google` / `naver` / `kakao` |
| `providerId` | string | — | `null` | 소셜 제공자 측 식별자 |
| `agreeTerms` | boolean | — | `true` | 약관 동의 |

```json
{
  "name": "김예공",
  "email": "guest@email.com",
  "password": "abcd1234!",
  "passwordCheck": "abcd1234!",
  "nickname": "예공이"
}
```

**응답 (201, `S0001`)**

```json
{
  "tid": 1705298638704,
  "status": { "code": "S0001", "msg": "리소스가 생성되었습니다" },
  "data": {
    "id": 4,
    "email": "guest@email.com",
    "name": "김예공",
    "nickname": "예공이",
    "phone": null,
    "emailConf": "2",
    "desc": null,
    "filePath": null,
    "role": "CLIENT",
    "state": 1,
    "extra": { "provider": "email" },
    "provider": "email",
    "providerId": null
  }
}
```

**에러**

| HTTP | detail | 원인 |
|---|---|---|
| 400 | `Password match failed` | `password ≠ passwordCheck` |
| 400 | `Email already registered` | 이메일 중복 |

> `role`은 항상 `CLIENT`로 고정 생성됩니다. 요청으로 지정할 수 없습니다.

---

#### `POST /api/auth/login` — 로그인

**인증** 불필요

**Request Body**

| 필드 | 타입 | 필수 |
|---|---|:-:|
| `email` | string(email) | ✅ |
| `password` | string | ✅ |

**응답 (200, `S0000`)**

```json
{
  "tid": 1705298638704,
  "status": { "code": "S0000", "msg": "성공" },
  "data": {
    "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "tokenType": "bearer"
  }
}
```

**에러** — 401 `Incorrect email or password` (존재하지 않는 계정과 비밀번호 불일치를 구분하지 않음)

---

#### `GET /api/auth/me` — 내 정보 조회

**인증** User · ⚠️ **이것만 `GET`입니다** (Body 없음)

**응답 `data`** — `signup` 응답과 동일 구조 (`password` 제외)

---

#### `POST /api/auth/exists` — 사용자 ID 존재 확인

**인증** 불필요

**Request** `{ "id": 4 }`
**응답 `data`** `{ "id": 4, "exists": true }`

---

#### `POST /api/auth/checkEmail` — 이메일 중복 확인

**인증** 불필요

**Request** `{ "email": "guest@email.com" }`
**응답 `data`** `{ "email": "guest@email.com", "exists": true }`

---

#### `POST /api/auth/logout` — 로그아웃

**인증** User · Body 없음

**응답 `data`** `{ "message": "Logged out successfully" }`

> ⚠️ **서버는 아무것도 하지 않습니다.** 토큰 블랙리스트가 없어 발급된 토큰은 만료 전까지 계속 유효합니다.
> 클라이언트가 저장소에서 토큰을 직접 삭제해야 합니다.

---

#### `POST /api/auth/update` — 내 정보 수정

**인증** User · 변경할 필드만 전송

**Request Body** (전부 선택)

| 필드 | 타입 | 설명 |
|---|---|---|
| `name` | string | |
| `nickname` | string | |
| `phone` | string | |
| `desc` | string | |
| `filePath` | string | 프로필 이미지 경로 |
| `extra` | object | 통째로 교체됨 (merge 아님) |
| `password` | string | **현재** 비밀번호 |
| `passwordNew` | string | 새 비밀번호 |
| `passwordNewCheck` | string | ⚠️ 받기만 하고 **검증하지 않음** |

비밀번호 변경 시 `password` + `passwordNew`를 함께 보내야 합니다.

**응답 `data`** `{ "message": "User updated successfully" }`

**에러**

| HTTP | detail |
|---|---|
| 400 | `No fields to update` — 변경할 필드가 하나도 없음 |
| 400 | `Current password incorrect` |
| 404 | `User not found` |

---

### 6.3 Files (`/api/files`)

Cloudflare R2 업로드를 담당합니다.

#### `POST /api/files/create` — 파일 업로드

**인증** User · **`multipart/form-data`** · **HTTP 201**

**Form Fields**

| 필드 | 타입 | 필수 | 설명 |
|---|---|:-:|---|
| `file` | File | ✅ | 이미지 파일 |
| `type` | string | ✅ | 업로드 종류 (아래 표) |
| `metadata` | string | — | **JSON 문자열**. 객체 아님 |

**`type` 허용값**

| 값 | R2 경로 | 파일명 규칙 |
|---|---|---|
| `profile` | `profiles/` | `p_{8자리hex}_{timestamp}.ext` |
| `prod` | `prod/` | `prod_{8자리hex}_{timestamp}.ext` |
| `reference` | `reference/` | `ref_{8자리hex}_{timestamp}.ext` |
| `snap` | `snaps/YYYY/MM/` | `snap_u{userId}_{timestamp}.ext` |
| `temp` | `temp/` | `tmp_{8자리hex}_{timestamp}.ext` |

**제약**

- 최대 **10 MB**
- 허용 MIME: `image/jpeg`, `image/png`, `image/gif`, `image/webp`, `image/bmp`

**응답 (201, `S0000`)**

```json
{
  "tid": 1705298638704,
  "status": { "code": "S0000", "msg": "성공" },
  "data": {
    "fileId": "9f2b7c1e4a8d4f0b9c3e5a7d1b2f4e60",
    "fileName": "IMG_0421.jpg",
    "fileKey": "snaps/2026/08/snap_u4_1754530800.jpg",
    "url": "https://pub-xxxx.r2.dev/snaps/2026/08/snap_u4_1754530800.jpg",
    "size": 2483920,
    "contentType": "image/jpeg",
    "meta": {},
    "cDate": 1754530800,
    "uDate": 1754530800
  }
}
```

> **`url`을 그대로 `snapUrl` / `imgUrl` / `thumbUrl` / `filePath`에 넣어 후속 API를 호출합니다.**

**에러**

| HTTP | detail |
|---|---|
| 400 | `'type' is required` / `Invalid type '{x}'. Allowed: [...]` |
| 400 | `metadata must be JSON string` |
| 413 | `Image too large (...). Max allowed: 10485760 bytes (10 MB)` |
| 415 | `Unsupported media type '{x}'. Allowed: [...]` |

---

#### `POST /api/files/list` · `get` · `delete` · `getPresigned`

| 엔드포인트 | Request | 응답 `data` |
|---|---|---|
| `/list` | 없음 | `{ "files": [FileMetadata], "total": 3 }` |
| `/get` | `{ "fileId": "..." }` | `FileMetadata` |
| `/delete` | `{ "fileId": "..." }` | `{ "fileId": "..." }` |
| `/getPresigned` | `{ "fileId": "..." }` | `{ "url": "https://...?X-Amz-..." }` (900초 유효) |

**에러** — 404 `file not found`

> ⚠️ **`fileId`는 서버 재시작 시 전부 사라집니다.** 파일 메타데이터가 DB가 아닌
> 프로세스 메모리(`_STORE` dict)에만 저장됩니다. R2의 실제 파일은 남지만
> `fileId`로는 더 이상 조회·삭제할 수 없습니다.
>
> **따라서 업로드 직후 받은 `url`을 반드시 즉시 사용하고 클라이언트가 보관하세요.**
> `fileId`를 장기 저장해서 나중에 조회하는 설계는 동작하지 않습니다.

---

### 6.4 Category (`/api/ctg`)

레퍼런스 이미지의 **구도 분류**입니다 (옷 분류 아님).
시드 데이터: `전신`, `상체 중심`, `하체 중심`, `셀카`, `내찍사`, `남찍사`

#### `POST /api/ctg/list`

**인증** User

**Request** `{ "page": 1, "limit": 20 }` — `page: 0`이면 전체 조회

**응답 `data`**

```json
{
  "items": [
    { "id": 1, "name": "전신", "cDate": 1712966400, "uDate": 1712966400 }
  ],
  "total": 6, "page": 1, "limit": 20
}
```

정렬은 `cDate ASC` 고정입니다.

#### `POST /api/ctg/get`

**Request** `{ "id": 1 }` → **응답 `data`** `CtgItem`

#### `POST /api/ctg/create`

**인증** User

| 필드 | 타입 | 필수 | 비고 |
|---|---|:-:|---|
| `userId` | int | ✅ | ⚠️ **필수지만 서버가 무시합니다.** 아무 값이나 넣으면 됩니다 |
| `name` | string | ✅ | 중복 불가 |

**에러** — 400 `Category name already exists`

#### `POST /api/ctg/update`

**Request** `{ "id": 1, "name": "전신샷" }` → **응답 `data`** `CtgItem`

#### `POST /api/ctg/delete`

**Request** `{ "id": 1 }` → **응답 `data`** `{ "id": 1, "deleted": true }`

> ⚠️ 해당 카테고리를 쓰는 레퍼런스 이미지가 있으면 FK 제약(`RESTRICT`)에 걸려
> **500 에러**가 납니다. 400이 아닙니다.

---

### 6.5 Reference (`/api/ref`)

**앱의 핵심 API.** 따라 찍을 목표 사진과 그 분석값(`aiDoc`)을 제공합니다.

#### `POST /api/ref/list` — 레퍼런스 목록

**인증** User

**Request**

```json
{
  "page": 1,
  "limit": 20,
  "filter": {
    "ctgId": 1,
    "title": "전신",
    "kwd": ["MOOD_CUTE", "CLOTH_TOP"]
  }
}
```

| 필터 | 타입 | 동작 |
|---|---|---|
| `ctgId` | int | 정확히 일치 |
| `title` | string | `LIKE %title%` 부분 일치 |
| `kwd` | array | `JSON_OVERLAPS` — 하나라도 겹치면 매칭 (**OR** 조건) |

`page: 0` → 전체 조회. 정렬은 `cDate DESC` 고정.

**응답 `data.items[]`** — 목록에는 `desc`와 `aiDoc`이 **포함되지 않습니다**

```json
{
  "imgId": 1001,
  "user": { "userId": 1, "nickname": "슈퍼어드민" },
  "ctg": { "ctgId": 1, "ctgName": "전신" },
  "imgUrl": "reference/ref_img1001_1760000000.png",
  "title": "멋진 사진",
  "useCnt": 100,
  "kwd": ["MOOD_CUTE", "CLOTH_TOP", "OUTER_CARDIGAN"],
  "expWeight": 0.85,
  "pri": 1,
  "cDate": 1760000000,
  "uDate": 1760000000
}
```

> ⚠️ `expWeight`(노출 가중치)와 `pri`(우선순위)는 내려오지만 **정렬에 쓰이지 않습니다.**
> 서버는 최신순으로만 반환합니다. 추천 정렬이 필요하면 클라이언트에서 직접 정렬하세요.

---

#### `POST /api/ref/get` — 레퍼런스 상세 ★

**인증** User

**Request** `{ "id": 1001 }`

**응답 `data`** — 목록 대비 `user.fileUrl`, `desc`, **`aiDoc`**이 추가됩니다

```json
{
  "imgId": 1001,
  "user": { "userId": 1, "nickname": "JohnDoe", "fileUrl": "profiles/p_user1_1760000000.jpg" },
  "ctg": { "ctgId": 1, "ctgName": "전신" },
  "imgUrl": "reference/ref_img1001_1760000000.png",
  "title": "멋진 사진",
  "desc": "이 사진은 정말 멋져요!",
  "useCnt": 100,
  "kwd": ["MOOD_CUTE", "CLOTH_TOP"],
  "expWeight": 0.85,
  "pri": 1,
  "cDate": 1760000000,
  "uDate": 1760000000,
  "aiDoc": { }
}
```

**`aiDoc` 구조** — 앱의 실시간 코칭(gate 0~5)이 대조하는 목표값입니다.

| 키 | 타입 | 설명 | 사용 gate |
|---|---|---|:-:|
| `aspectRatio` | string | 목표 화면비 (`"16:9"`) | 0 |
| `size` | `{w, h}` | 원본 크기 | — |
| `focalLengthInfo` | object | `{focalLengthMM, source, confidence, lensType}` | 1 |
| `exif` | object | 원본 EXIF (조리개/ISO/렌즈) | 1 |
| `estimatedDistance` | float | 피사체 거리 (m) | 2 |
| `shoulderRatio` | float | 어깨 폭 비율 | 2 |
| `bbox` | string | 인물 영역. **16자리 Hex** (`x,y,w,h` 각 4자리) | 2 |
| `geoCalib` | object | `{pitchDegrees, rollDegrees, vfovDegrees, focalLengthPx, ...}` | 3 |
| `framing` | object | `{headroom, leadRoom, camAngle, bodyCoverage, ...}` | 4 |
| `compositionType` | string | `"ruleOfThirdsLeftUpper"` 등 | 4 |
| `keypoints` | string | **관절 133개. 가변 Hex** (디코딩은 `src/sql/DATABASE.md` 참고) | 5 |
| `shotType` | string | `"mediumShot"` 등 | — |
| `silhouette` | object | `{frameRatio, segmentationBackend, maskConfidence}` | — |
| `depth` | object | `{compressionIndex}` | — |

> **Hex 인코딩 규격(`kp` / `pv` / `bbox`)의 디코딩 코드는 [`src/sql/DATABASE.md`](../sql/DATABASE.md) 후반부에 있습니다.**
> `aiDoc`은 스키마가 고정되지 않은 자유 JSON이므로, 클라이언트는 **키가 없는 경우를 항상 방어**해야 합니다.

**에러** — 404 `Reference image not found`

---

#### `POST /api/ref/create` — 레퍼런스 등록

**인증** User ⚠️ (Admin 아님 — 일반 사용자도 등록 가능)

| 필드 | 타입 | 필수 | 기본값 |
|---|---|:-:|---|
| `ctgId` | int | ✅ | — |
| `imgUrl` | string | ✅ | — |
| `title` | string | — | `null` |
| `desc` | string | — | `null` |
| `kwd` | array | — | `null` |
| `aiDoc` | object | — | `null` |
| `expWeight` | float | — | `0` |
| `pri` | int | — | `0` |

`userId`는 JWT에서 자동 주입되며, `useCnt`는 항상 `0`으로 생성됩니다.

**응답 `data`** — 생성된 `RefItem` 전체
**에러** — 400 `Category not found`

#### `POST /api/ref/update`

`id` 필수 + 변경할 필드만. `useCnt`도 수정 가능합니다.
**에러** — 400 `No fields to update`, 404 `Reference image not found`

#### `POST /api/ref/delete`

**Request** `{ "id": 1001 }` → **응답 `data`** `{ "id": 1001, "deleted": true }`

> ⚠️ 이 이미지를 참조하는 세션/스냅이 있으면 FK `RESTRICT`로 **500 에러**가 납니다.

---

### 6.6 Product (`/api/prod`)

#### `POST /api/prod/list`

**인증** User

**Request**

```json
{ "page": 1, "limit": 20, "filter": { "name": "셔츠", "pStat": 1 } }
```

| 필터 | 동작 |
|---|---|
| `name` | `LIKE %name%` 부분 일치 |
| `pStat` | 정확히 일치. `0`/`1`/`2`만 허용 |

정렬 `cDate DESC` 고정. `page: 0` **미지원**.

**응답 `data.items[]`**

```json
{
  "id": 7,
  "userName": "관리자",
  "name": "옥스포드 셔츠",
  "brand": "무신사 스탠다드",
  "price": 39000,
  "thumbUrl": "prod/prod_a1b2c3d4_1754530800.webp",
  "pStat": 1,
  "cDate": 1754530800,
  "uDate": 1754530800
}
```

> `userName`은 `nickname → name → email` 순으로 폴백된 등록자 표시명입니다.
> 원본 `userId`는 응답에 포함되지 않습니다.

#### `POST /api/prod/get`

**Request** `{ "id": 7 }` → **응답 `data`** `ProdItem` · **에러** 404 `Product not found`

#### `POST /api/prod/create` — **Admin**

| 필드 | 타입 | 필수 | 기본값 |
|---|---|:-:|---|
| `name` | string | ✅ | — |
| `brand` | string | — | `null` |
| `price` | int | — | `0` (음수 불가) |
| `thumbUrl` | string | — | `null` |
| `pStat` | int | — | `1` |

#### `POST /api/prod/update` · `delete` — **Admin**

`update`: `id` 필수 + 변경 필드만 → `ProdItem`
`delete`: `{ "id": 7 }` → `{ "id": 7 }`

**에러** — 400 `Invalid pStat value`, 400 `No fields to update`, 404 `Product not found`

> ⚠️ 상품에 연결된 스냅이 있으면 삭제 시 FK `RESTRICT`로 **500 에러**가 납니다.

---

### 6.7 Session (`/api/session`)

촬영 시도 1회를 기록합니다. **네트워크 연결이 아니라 논리적 기록 단위**입니다.

#### `POST /api/session/start` — 세션 시작 ★

**인증** User

**Request**

| 필드 | 타입 | 필수 | 설명 |
|---|---|:-:|---|
| `imgId` | int | ✅ | 참조할 레퍼런스 이미지 ID |
| `device` | object | — | 기기 메타데이터 (자유 JSON) |

```json
{
  "imgId": 1001,
  "device": { "model": "iPhone 15 Pro", "os": "iOS 18.2", "screen": "1179x2556" }
}
```

**응답** — ⚠️ **HTTP는 200인데 body code는 `S0001`입니다** (불일치)

```json
{
  "tid": 1705298638704,
  "status": { "code": "S0001", "msg": "리소스가 생성되었습니다" },
  "data": {
    "id": "a3f8b2c1d4e5f60718293a4b5c6d7e8f",
    "userId": 4,
    "userName": "예공이",
    "imgId": 1001,
    "sDate": 1754530800,
    "eDate": null,
    "device": { "model": "iPhone 15 Pro" },
    "sStat": 0,
    "cDate": 1754530800,
    "uDate": 1754530800
  }
}
```

**`data.id`(32자 문자열)를 저장해 두었다가 이후 `snap/create`와 `session/end`에 사용합니다.**

**에러**

| HTTP | detail |
|---|---|
| 404 | `Reference image not found` |
| 500 | `Failed to start session` |
| 503 | `Could not allocate unique session ID` (ID 충돌 5회 재시도 실패) |

---

#### `POST /api/session/end` — 세션 종료

**인증** User

**Request** `{ "id": "a3f8b2c1..." }`

**응답 `data`** — `sStat: 1`, `eDate` 채워진 `SessionItem`

**에러**

| HTTP | detail | 원인 |
|---|---|---|
| 404 | `Session not found` | |
| 409 | `Session already closed` | 이미 종료된 세션 (`sStat ≠ 0`) |

> ⚠️ **소유권을 검사하지 않습니다.** 세션 ID만 알면 남의 세션도 종료됩니다.
> 또한 `end`를 호출하지 않으면 세션은 **영구히 `READY`(0) 상태로 남습니다.**
> 자동 만료 로직이 없으니 앱이 반드시 호출하세요 (백그라운드 진입/앱 종료 시 포함).

---

#### `POST /api/session/list` — 세션 목록

**인증** User

**Request** — `filter` 객체 또는 flat 방식 둘 다 지원 (하위 호환)

```json
{ "page": 1, "limit": 20,
  "filter": { "userId": 4, "imgId": 1001, "sStat": 0, "sDate": 1754400000, "eDate": 1754600000 } }
```

| 필터 | 동작 |
|---|---|
| `userId` / `imgId` / `sStat` | 정확히 일치 |
| `sDate` | 세션 **시작일 >= 값** |
| `eDate` | 세션 **시작일 <= 값** ⚠️ 종료일이 아니라 시작일 기준입니다 |

정렬 `sDate DESC` 고정.

> ⚠️ **소유권 필터가 자동 적용되지 않습니다.** `userId`를 지정하지 않으면
> **전체 사용자의 세션이 반환됩니다.** 마이페이지 용도라면 클라이언트가
> `filter.userId`를 반드시 명시해야 합니다.

---

#### `POST /api/session/detail` — 세션 상세

**인증** User · **소유자 또는 Admin만 조회 가능**

**Request** `{ "id": "a3f8b2c1..." }`

**응답 `data`** — ⚠️ **`session` 키로 한 번 더 감싸집니다**

```json
{
  "data": {
    "session": { "id": "a3f8b2c1...", "userId": 4, "sStat": 0, "...": "..." }
  }
}
```

**에러** — 403 `Session access denied`, 404 `Session not found`

---

### 6.8 Snap (`/api/snap`)

촬영 결과물 + 후기 + 체형 아카이브.

#### `POST /api/snap/create` — 스냅 등록

**인증** User

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|---|---|:-:|---|---|
| `prodId` | int | ✅ | — | **상품 필수.** 없으면 등록 불가 |
| `imgId` | int | ✅ | — | 참조한 레퍼런스 |
| `sId` | string | ✅ | — | 세션 ID |
| `snapUrl` | string | ✅ | — | `files/create` 응답의 `url` |
| `comment` | string | — | `null` | 후기 |
| `gender` | int | — | `0` | `0`=UNKNOWN, `1`=MALE, `2`=FEMALE |
| `userH` | float | — | `null` | 키 (cm) |
| `userW` | float | — | `null` | 몸무게 (kg) |

**응답 `data`** — 생성된 `SnapItem` 전체 (`viewCnt`는 `0`)

**에러**

| HTTP | detail |
|---|---|
| 400 | `sId is required` / `Invalid gender value` |
| 400 | `Product not found` / `Reference image not found` / `Session not found` |
| 409 | `Session already has a snap` — **세션당 스냅은 1개만** |

---

#### `POST /api/snap/list` — 스냅 목록

**인증** User

```json
{
  "page": 1, "limit": 20,
  "filter": { "userId": 4, "prodId": 7, "imgId": 1001,
              "fromDate": 1754400000, "toDate": 1754600000 },
  "sortBy": "cDate",
  "sortOrder": "desc"
}
```

| 필드 | 허용값 | 기본값 |
|---|---|---|
| `sortBy` | `cDate` / `uDate` / `viewCnt` / `id` | `cDate` |
| `sortOrder` | `asc` / `desc` | `desc` |

> `sortBy`·`sortOrder`는 `filter` 밖 최상위에 둡니다.
> `fromDate`/`toDate`는 **초·밀리초 둘 다 허용**됩니다 (13자리면 서버가 자동 환산).

**응답 `data.items[]`** — ⚠️ **목록에는 `comment`·`gender`·`userH`·`userW`가 없습니다**

```json
{
  "id": 5001, "userId": 4, "userName": "예공이",
  "prodId": 7, "imgId": 1001, "sId": "a3f8b2c1...",
  "snapUrl": "https://pub-xxxx.r2.dev/snaps/2026/08/snap_u4_1754530800.jpg",
  "viewCnt": 0, "cDate": 1754530800, "uDate": 1754530800
}
```

후기·체형이 필요하면 `/api/snap/get`을 별도 호출해야 합니다.

**에러** — 400 `Invalid sortBy value` / `Invalid sortOrder value` / `fromDate must be less than or equal to toDate`

> ⚠️ **`sortBy: "viewCnt"`는 사실상 무의미합니다.** 서버가 조회수를 자동 증가시키지 않아
> 모든 스냅의 `viewCnt`가 `0`으로 고정되어 있습니다.
>
> ⚠️ **공개/비공개 구분이 없습니다.** 로그인한 모든 사용자가 전체 스냅을 조회할 수 있고,
> 상세 조회 시 키·몸무게까지 노출됩니다.

---

#### `POST /api/snap/get` — 스냅 상세

**Request** `{ "id": 5001 }`

**응답 `data`** — 목록 필드 + `comment`, `gender`, `userH`, `userW`

**에러** — 404 `Snap not found`

#### `POST /api/snap/update` — **Admin**

`id` 필수 + 변경 필드만. `viewCnt`도 수정 가능.
`sId`에 빈 문자열(`""`)을 보내면 세션 연결 해제(NULL)됩니다.

#### `POST /api/snap/delete` — **Admin**

**Request** `{ "id": 5001 }` → **응답 `data`** `{ "id": 5001 }`

> ⚠️ 스냅을 작성한 본인도 수정·삭제할 수 없습니다. **Admin 전용**입니다.

---

## 7. Enum / 상수 레퍼런스

### UserRole (문자열)

| 값 | 설명 |
|---|---|
| `SUPER_ADMIN` | 최고 관리자 |
| `ADMIN` | 운영 관리자 |
| `CLIENT` | 일반 사용자 (가입 시 기본값) |

### UserState — `state`

| 값 | 설명 |
|---|---|
| `0` | INACTIVE — 로그인 불가 |
| `1` | ACTIVE |

### emailConf ⚠️ **문자열입니다**

| 값 | 설명 |
|---|---|
| `"1"` | 인증 완료 |
| `"2"` | 미인증 (기본값) |

### SessionStatus — `sStat`

| 값 | 설명 | 비고 |
|---|---|---|
| `0` | READY | 진행 중 (`eDate`가 `null`) |
| `1` | COMPLETED | 정상 종료 |
| `2` | AUTO_TERM | 자동 종료 — **서버가 설정하는 코드 없음** |
| `3` | FAILED | ⚠️ **DB CHECK 제약이 `0~2`만 허용해 저장 시 실패** |

### ProductStatus — `pStat`

| 값 | 설명 |
|---|---|
| `0` | INACTIVE |
| `1` | ACTIVE (기본값) |
| `2` | SOLD_OUT |

### Gender — `gender`

| 값 | 설명 |
|---|---|
| `0` | UNKNOWN (기본값) |
| `1` | MALE |
| `2` | FEMALE |

### 키워드 코드 (`kwd`)

`tb_tag`에 시드된 코드 문자열 배열입니다. **조회 API가 없어 코드를 클라이언트에 하드코딩해야 합니다.**

| 계열 | 예시 |
|---|---|
| 분위기 | `MOOD_CUTE`, `MOOD_Y2K`, `MOOD_STREET`, `MOOD_CHIC`, `MOOD_REFRESH`, `MOOD_VINTAGE` |
| 상의 | `TOP_LONGSLEEVE`, `TOP_TSHIRT`, `TOP_SWEATSHIRT`, `TOP_SHIRT`, `TOP_HOODIE` … |
| 아우터 | `OUTER_CARDIGAN`, `OUTER_COAT`, `OUTER_LONGPADDING`, `OUTER_LEATHER` … |
| 하의 | `BOTTOM_DENIM`, `BOTTOM_SLACKS`, `BOTTOM_SHORTS` … |
| 신발 | `SHOES_SNEAKERS`, `SHOES_BOOTS`, `SHOES_SANDALS` … |
| 가방·잡화 | `BAG_CROSS`, `BAG_TOTE`, `ACC_HAT`, `ACC_WATCH` … |

전체 목록은 [`src/sql/init/tryangle-seed.sql`](../sql/init/tryangle-seed.sql) 참고.

---

## 8. 전체 플로우 예제

촬영 1회의 전체 호출 순서입니다.

```
1) 로그인
   POST /api/auth/login          { email, password }
   → data.accessToken 저장. 이후 모든 요청에 Authorization 헤더

2) 카테고리 목록
   POST /api/ctg/list            { page: 0 }
   → 전신 / 상체 중심 / 셀카 …

3) 레퍼런스 탐색
   POST /api/ref/list            { page: 1, limit: 20, filter: { ctgId: 1 } }
   → 썸네일 그리드 렌더

4) 레퍼런스 선택  ★
   POST /api/ref/get             { id: 1001 }
   → data.aiDoc 확보. 앱 코칭 엔진에 목표값 주입

5) 세션 시작
   POST /api/session/start       { imgId: 1001, device: {...} }
   → data.id (32자 sId) 보관

   ────── 앱 내부 온디바이스 코칭 (gate 0~5). 서버 호출 없음 ──────

6) 결과 사진 업로드
   POST /api/files/create        multipart: file, type="snap"
   → data.url 확보

7) 상품 선택
   POST /api/prod/list           { page: 1, limit: 50 }
   → 사용자가 착용 상품 선택

8) 스냅 등록
   POST /api/snap/create         { prodId, imgId, sId, snapUrl,
                                   comment, gender, userH, userW }

9) 세션 종료
   POST /api/session/end         { id: sId }

10) 피드 조회
   POST /api/snap/list           { page: 1, limit: 20,
                                   filter: { prodId: 7 } }
```

> **6·8단계는 반드시 순서대로**입니다 (`snapUrl`이 필요). **8·9단계는 순서 무관**합니다.

---

## 9. 알려진 이슈 (반드시 확인)

프론트엔드 구현 시 영향을 주는 사항입니다.

### 🔴 서버 기동 불가 (2026-08-07 기준)

`main` 브랜치는 **임포트 단계에서 실패해 실행되지 않습니다.** 삭제된 모듈
(`src.utils.db_utils`, `src.core.id_generator`, `src.modules.system_monitor`)을
참조 중이고, `src/core/responses.py`의 성공 응답 헬퍼에도 버그가 있습니다.
**API 연동 전 백엔드 담당자에게 기동 가능 여부를 먼저 확인하세요.**

### 🟠 계약에 영향을 주는 사항

| # | 내용 | 대응 |
|---|---|---|
| 1 | **에러 응답이 공통 포맷이 아님** (`{"detail": ...}`) | HTTP status로 분기 |
| 2 | **`/api/health`만 응답 구조가 다름** | 별도 파서 사용 |
| 3 | **`fileId`가 서버 재시작 시 소멸** (메모리 저장) | 업로드 즉시 `url` 사용·보관 |
| 4 | **`session/start`가 HTTP 200 + `S0001`** | body code에 의존하지 말 것 |
| 5 | **`session/detail` 응답이 `data.session`으로 한 겹 더 감싸짐** | 다른 상세 API와 파서 분리 |
| 6 | **`session/list`에 소유권 필터 없음** | `filter.userId` 항상 명시 |
| 7 | **`snap/list`에 후기·체형 없음** | 상세는 `snap/get` 별도 호출 |
| 8 | **`viewCnt`가 증가하지 않음** | 인기순 정렬 사용 보류 |
| 9 | **`ctg/create`의 `userId`가 무시됨** | 필수지만 값은 의미 없음 |
| 10 | **`page: 0` 지원이 엔드포인트마다 다름** | [5장](#5-페이지네이션) 표 참고 |
| 11 | **로그아웃이 토큰을 무효화하지 않음** | 클라이언트가 직접 삭제 |
| 12 | **FK 위반 시 400이 아닌 500** | 삭제 실패를 500으로도 처리 |
| 13 | **`sStat: 3`(FAILED) 저장 불가** | DB 제약 수정 전까지 미사용 |
| 14 | **`passwordNewCheck` 미검증** | 클라이언트에서 일치 확인 |

### 🟡 미구현 (Postman 컬렉션에는 있으나 서버에 없음)

- `/api/tag/*` — 태그 CRUD. `kwd` 코드는 하드코딩 필요
- `/api/bmk/*` — 북마크
- `/api/system/log`, `/api/system/search` — 로그 수집·검색 (라우터 미등록)
- 체형(`userH`/`userW`/`gender`) 기반 스냅 검색
- 레퍼런스 추천 정렬 (`expWeight`/`pri` 미사용)

### 🟡 참고 문서

- 기존 `try-angle-server.postman_collection.json`은 **JSON 문법 오류(trailing comma)로 임포트되지 않으며**, 내용도 현재 코드와 불일치합니다. 본 문서를 기준으로 삼으세요.
- Hex 인코딩 규격(`kp`/`pv`/`bbox`) 및 DB 스키마: [`src/sql/DATABASE.md`](../sql/DATABASE.md)
