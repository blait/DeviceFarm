# AWS Device Farm 브라우저별 FPS 측정 가이드

> AWS Device Farm TestGrid를 활용하여 데스크톱 브라우저(Chrome, Firefox, Edge)에서 웹앱의 FPS 및 성능을 측정하는 가이드입니다.

---

## 1. 사전 준비

### 1.1 필수 요구사항

| 항목 | 설명 |
|------|------|
| AWS 계정 | Device Farm 접근 권한이 있는 IAM 사용자 |
| AWS CLI | v2 이상 설치 및 설정 완료 |
| Python | 3.8 이상 |
| pip | Python 패키지 관리자 |

### 1.2 AWS CLI 설치

```bash
# macOS
brew install awscli

# Linux
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# 설치 확인
aws --version
```

### 1.3 AWS CLI 자격 증명 설정

```bash
aws configure
# AWS Access Key ID: <YOUR_ACCESS_KEY>
# AWS Secret Access Key: <YOUR_SECRET_KEY>
# Default region name: us-west-2
# Default output format: json
```

> ⚠️ Device Farm은 **us-west-2 (Oregon) 리전에서만** 사용 가능합니다.

### 1.4 IAM 권한

사용자에게 다음 권한이 필요합니다:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "devicefarm:CreateTestGridProject",
                "devicefarm:CreateTestGridUrl",
                "devicefarm:ListTestGridProjects",
                "devicefarm:ListTestGridSessions",
                "devicefarm:ListTestGridSessionActions",
                "devicefarm:ListTestGridSessionArtifacts"
            ],
            "Resource": "*"
        }
    ]
}
```

### 1.5 Python 의존성 설치

```bash
pip install -r requirements.txt
```

---

## 2. 프로젝트 생성

### 2.1 TestGrid 프로젝트 생성

```bash
aws devicefarm create-test-grid-project \
    --name "browser-fps-test" \
    --region us-west-2
```

응답 예시:
```json
{
    "testGridProject": {
        "arn": "arn:aws:devicefarm:us-west-2:123456789012:testgrid-project:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "name": "browser-fps-test",
        "created": "2026-03-12T00:00:00.000000+09:00"
    }
}
```

> 응답의 `arn` 값을 복사해두세요. 테스트 실행 시 필요합니다.

### 2.2 기존 프로젝트 확인

```bash
aws devicefarm list-test-grid-projects --region us-west-2
```

---

## 3. 테스트 실행

### 3.1 설정 파일 수정

`config.json`을 열어 환경에 맞게 수정합니다:

```json
{
    "project_arn": "arn:aws:devicefarm:us-west-2:123456789012:testgrid-project:xxxxxxxx",
    "target_url": "https://www.naver.com",
    "fps_duration_seconds": 3,
    "browsers": [
        {"browserName": "chrome", "browserVersion": "latest"},
        {"browserName": "firefox", "browserVersion": "latest"},
        {"browserName": "MicrosoftEdge", "browserVersion": "latest"}
    ]
}
```

### 3.2 테스트 실행

```bash
python browser_fps_test.py
```

### 3.3 특정 URL만 테스트

```bash
python browser_fps_test.py --url https://www.example.com
```

### 3.4 특정 브라우저만 테스트

```bash
python browser_fps_test.py --browser chrome
```

---

## 4. 결과 해석

### 4.1 출력 예시

```
==================================================
SUMMARY
==================================================
Browser      FPS(idle)    FPS(scroll)  DOM(ms)    LongTasks
----------------------------------------------------------
chrome       64           64           1903       0
firefox      39           47           3238       0
MicrosoftEdge 65           64           2144       0
```

### 4.2 측정 항목 설명

| 항목 | 설명 | 기준 |
|------|------|------|
| FPS (idle) | 페이지 로드 후 대기 상태의 프레임 레이트 | 60 이상이면 양호 |
| FPS (scroll) | 스크롤 동작 후 프레임 레이트 | 60 이상이면 양호 |
| First Paint | 첫 번째 픽셀이 화면에 그려지는 시간 | 1초 이내 권장 |
| First Contentful Paint | 첫 번째 콘텐츠가 렌더링되는 시간 | 1.8초 이내 권장 |
| DOM Complete | DOM 파싱 완료 시간 | 3초 이내 권장 |
| Long Tasks | 50ms 이상 걸린 작업 수 | 0에 가까울수록 좋음 |

### 4.3 FPS 측정 원리

#### requestAnimationFrame이란?

`requestAnimationFrame`은 브라우저가 제공하는 JavaScript API로, **"다음에 화면을 다시 그릴 때 이 함수를 실행해줘"** 라고 브라우저에 요청하는 것입니다.

브라우저는 화면을 초당 60번(60Hz 모니터 기준) 다시 그리는데, 매번 그리기 직전에 등록된 콜백 함수를 호출합니다. 이 특성을 이용하면 실제로 화면이 몇 번 갱신되는지 셀 수 있습니다.

```
모니터 주사율 60Hz인 경우:

1초에 화면을 60번 그림
→ requestAnimationFrame 콜백도 60번 호출됨
→ FPS = 60

브라우저가 무거운 작업으로 버벅이면:
→ 1초에 화면을 30번만 그림
→ 콜백도 30번만 호출됨
→ FPS = 30 (프레임 드롭 발생)
```

#### 측정 방식

설정된 시간(기본 3초) 동안 콜백 호출 횟수를 세어 FPS를 계산합니다.

```javascript
let frames = 0;
let start = performance.now();

function count() {
    frames++;                              // 프레임 카운트
    if (performance.now() - start < 3000)  // 3초 동안
        requestAnimationFrame(count);      // 다음 프레임에 다시 호출
    else
        console.log(frames / 3);           // FPS = 총 프레임 / 초
}
requestAnimationFrame(count);
```

#### 한계

- GPU 레벨의 정밀한 프레임 타임 측정은 아닙니다
- 브라우저 탭이 비활성 상태이면 호출 빈도가 낮아져 부정확해질 수 있습니다
- 브라우저 간 **상대적 성능 비교** 용도로 활용하는 것을 권장합니다

---

## 5. 세션 기록 확인

### 5.1 세션 목록 조회

```bash
aws devicefarm list-test-grid-sessions \
    --project-arn "arn:aws:devicefarm:us-west-2:123456789012:testgrid-project:xxxxxxxx" \
    --region us-west-2
```

### 5.2 세션 상세 액션 조회

```bash
aws devicefarm list-test-grid-session-actions \
    --session-arn "arn:aws:devicefarm:us-west-2:123456789012:testgrid-session:xxxxxxxx/yyyyyyyy" \
    --region us-west-2
```

### 5.3 세션 아티팩트(영상/로그) 조회

```bash
aws devicefarm list-test-grid-session-artifacts \
    --session-arn "arn:aws:devicefarm:us-west-2:123456789012:testgrid-session:xxxxxxxx/yyyyyyyy" \
    --region us-west-2
```

---

## 6. 비용

| 항목 | 단가 |
|------|------|
| 데스크톱 브라우저 테스트 | $0.005 / 인스턴스 분 |
| 무료 체험 | 없음 (데스크톱 브라우저는 무료 체험 미포함) |

예시: Chrome + Firefox + Edge 각 1분씩 = 3분 × $0.005 = **$0.015**

---

## 7. 지원 브라우저

| 브라우저 | 지원 여부 | 비고 |
|---------|----------|------|
| Chrome | ✅ | latest 또는 특정 버전 지정 가능 |
| Firefox | ✅ | latest 또는 특정 버전 지정 가능 |
| Microsoft Edge | ✅ | `ms:edgeChromium: true` 필수 |
| Safari | ❌ | TestGrid 미지원 |

---

## 8. 주의사항

- Device Farm TestGrid는 **EC2 Windows 인스턴스** 위에서 브라우저를 실행합니다. 실제 사용자 PC 환경과 하드웨어 성능이 다를 수 있습니다.
- FPS 측정은 `requestAnimationFrame` 기반이므로 GPU 레벨의 정밀한 프레임 타임 측정은 아닙니다.
- 브라우저 간 **상대적 성능 비교** 용도로 활용하는 것을 권장합니다.
- TestGrid 세션 URL은 발급 후 **5분간 유효**합니다 (설정 변경 가능).

---

## 9. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `AccessDeniedException` | IAM 권한 부족 | 2장의 IAM 정책 확인 |
| `The capability ms:edgeChromium must be set to true` | Edge 옵션 누락 | config.json에서 Edge 설정 확인 |
| `Session URL expired` | 세션 URL 만료 | `expires-in-seconds` 값 증가 |
| FPS가 비정상적으로 낮음 | 탭 비활성 상태 | 테스트 중 다른 작업 없이 실행 |

---

## 참고 자료

- [AWS Device Farm TestGrid 문서](https://docs.aws.amazon.com/devicefarm/latest/testgrid/what-is-testgrid.html)
- [Device Farm CLI Reference](https://docs.aws.amazon.com/cli/latest/reference/devicefarm/)
- [Selenium WebDriver 문서](https://www.selenium.dev/documentation/)
- [requestAnimationFrame MDN](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame)
