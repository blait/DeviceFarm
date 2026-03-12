#!/bin/bash
# AWS Device Farm 브라우저 FPS 테스트 - 빠른 시작 스크립트
# 아무것도 없는 상태에서 이 스크립트 하나로 환경 구성 + 테스트 실행까지 완료됩니다.

set -e

echo "============================================"
echo " AWS Device Farm Browser FPS Test - Setup"
echo "============================================"

# 1. AWS CLI 확인
echo ""
echo "[1/5] AWS CLI 확인..."
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI가 설치되어 있지 않습니다."
    echo ""
    echo "설치 방법:"
    echo "  macOS:  brew install awscli"
    echo "  Linux:  curl 'https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip' -o 'awscliv2.zip' && unzip awscliv2.zip && sudo ./aws/install"
    exit 1
fi
echo "✅ AWS CLI $(aws --version | head -1)"

# 2. AWS 자격 증명 확인
echo ""
echo "[2/5] AWS 자격 증명 확인..."
if ! aws sts get-caller-identity --region us-west-2 &> /dev/null; then
    echo "❌ AWS 자격 증명이 설정되지 않았습니다."
    echo "   aws configure 를 실행하여 설정하세요. (리전: us-west-2)"
    exit 1
fi
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region us-west-2)
echo "✅ AWS Account: ${ACCOUNT_ID}"

# 3. Python 확인 및 의존성 설치
echo ""
echo "[3/5] Python 환경 설정..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3이 설치되어 있지 않습니다."
    exit 1
fi
echo "✅ $(python3 --version)"
pip3 install -r requirements.txt -q
echo "✅ 의존성 설치 완료"

# 4. TestGrid 프로젝트 생성
echo ""
echo "[4/5] Device Farm TestGrid 프로젝트 확인..."
EXISTING=$(aws devicefarm list-test-grid-projects --region us-west-2 --query 'testGridProjects[?name==`browser-fps-test`].arn' --output text 2>/dev/null)

if [ -n "$EXISTING" ] && [ "$EXISTING" != "None" ]; then
    echo "✅ 기존 프로젝트 사용: $EXISTING"
    PROJECT_ARN="$EXISTING"
else
    echo "   프로젝트 생성 중..."
    PROJECT_ARN=$(aws devicefarm create-test-grid-project --name "browser-fps-test" --region us-west-2 --query 'testGridProject.arn' --output text)
    echo "✅ 프로젝트 생성 완료: $PROJECT_ARN"
fi

# config.json 업데이트
python3 -c "
import json
with open('config.json') as f: c = json.load(f)
c['project_arn'] = '$PROJECT_ARN'
with open('config.json', 'w') as f: json.dump(c, f, indent=4)
"
echo "✅ config.json 업데이트 완료"

# 5. 테스트 실행
echo ""
echo "[5/5] FPS 테스트 실행..."
echo "============================================"
echo ""
python3 browser_fps_test.py "$@"
