#!/usr/bin/env python3
"""
AWS Device Farm TestGrid - Browser FPS Test

데스크톱 브라우저(Chrome, Firefox, Edge)에서 웹앱의 FPS 및 성능을 측정합니다.

사전 준비:
  1. AWS CLI 설치 및 자격 증명 설정 (리전: us-west-2)
  2. pip install -r requirements.txt
  3. config.json에 project_arn 설정

사용법:
  python browser_fps_test.py                          # config.json 기본 설정으로 실행
  python browser_fps_test.py --url https://example.com  # 특정 URL 테스트
  python browser_fps_test.py --browser chrome           # 특정 브라우저만 테스트
  python browser_fps_test.py --setup                    # TestGrid 프로젝트 자동 생성
"""

import argparse
import subprocess
import json
import sys
import time
import os
from datetime import datetime
from selenium import webdriver

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

FPS_SCRIPT_TEMPLATE = """
return new Promise(resolve => {{
    let frames = 0;
    let start = performance.now();
    function count() {{
        frames++;
        if (performance.now() - start < {duration}) {{
            requestAnimationFrame(count);
        }} else {{
            let elapsed = (performance.now() - start) / 1000;
            resolve({{fps: Math.round(frames / elapsed), frames: frames, seconds: elapsed}});
        }}
    }}
    requestAnimationFrame(count);
}});
"""

PERF_SCRIPT = """
return JSON.stringify({
    longTasks: performance.getEntriesByType('longtask').length,
    paint: performance.getEntriesByType('paint').map(e => ({name: e.name, startTime: Math.round(e.startTime)})),
    navigation: (() => {
        let n = performance.getEntriesByType('navigation')[0];
        return n ? {domComplete: Math.round(n.domComplete), loadEvent: Math.round(n.loadEventEnd)} : null;
    })()
});
"""


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def setup_project():
    """TestGrid 프로젝트를 생성하고 config.json에 ARN을 저장합니다."""
    print("TestGrid 프로젝트 생성 중...")
    result = subprocess.run(
        ["aws", "devicefarm", "create-test-grid-project",
         "--name", "browser-fps-test",
         "--region", "us-west-2"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"프로젝트 생성 실패: {result.stderr}")
        sys.exit(1)

    data = json.loads(result.stdout)
    arn = data["testGridProject"]["arn"]
    print(f"프로젝트 생성 완료: {arn}")

    config = load_config()
    config["project_arn"] = arn
    save_config(config)
    print("config.json에 project_arn 저장 완료.")
    return arn


def create_session(project_arn, expires_seconds=300):
    """TestGrid 세션 URL을 발급합니다."""
    result = subprocess.run(
        ["aws", "devicefarm", "create-test-grid-url",
         "--project-arn", project_arn,
         "--expires-in-seconds", str(expires_seconds),
         "--region", "us-west-2"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"세션 생성 실패: {result.stderr}")
        sys.exit(1)

    return json.loads(result.stdout)["url"]


def create_driver(hub_url, browser_config):
    """브라우저별 WebDriver를 생성합니다."""
    name = browser_config["browserName"]
    if name == "chrome":
        options = webdriver.ChromeOptions()
    elif name == "firefox":
        options = webdriver.FirefoxOptions()
    elif name == "MicrosoftEdge":
        options = webdriver.EdgeOptions()
        options.set_capability("ms:edgeChromium", True)
    else:
        raise ValueError(f"지원하지 않는 브라우저: {name}")

    options.browser_version = browser_config["browserVersion"]
    return webdriver.Remote(command_executor=hub_url, options=options)


def run_fps_test(hub_url, browser_config, target_url, fps_duration_ms):
    """단일 브라우저에서 FPS 및 성능을 측정합니다."""
    name = browser_config["browserName"]
    print(f"\n{'='*50}")
    print(f"Testing: {name} {browser_config['browserVersion']}")
    print(f"URL: {target_url}")
    print(f"{'='*50}")

    driver = create_driver(hub_url, browser_config)
    fps_script = FPS_SCRIPT_TEMPLATE.format(duration=fps_duration_ms)

    try:
        driver.get(target_url)
        time.sleep(3)

        print(f"Page loaded: {driver.title}")
        print(f"Window size: {driver.get_window_size()}")

        # FPS 측정 (대기 상태)
        fps_result = driver.execute_script(fps_script)
        print(f"\n[FPS - Idle]")
        print(f"  FPS: {fps_result['fps']}")
        print(f"  Frames: {fps_result['frames']}")
        print(f"  Duration: {fps_result['seconds']:.2f}s")

        # 성능 데이터
        perf = json.loads(driver.execute_script(PERF_SCRIPT))
        print(f"\n[Performance]")
        print(f"  Long Tasks: {perf['longTasks']}")
        for p in perf.get("paint", []):
            print(f"  {p['name']}: {p['startTime']}ms")
        if perf.get("navigation"):
            print(f"  DOM Complete: {perf['navigation']['domComplete']}ms")
            print(f"  Load Event: {perf['navigation']['loadEvent']}ms")

        # 스크롤 후 FPS
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        fps_scroll = driver.execute_script(fps_script)
        print(f"\n[FPS - After Scroll]")
        print(f"  FPS: {fps_scroll['fps']}")

        return {
            "browser": name,
            "version": browser_config["browserVersion"],
            "fps_idle": fps_result["fps"],
            "fps_scroll": fps_scroll["fps"],
            "first_paint": next((p["startTime"] for p in perf.get("paint", []) if p["name"] == "first-paint"), None),
            "fcp": next((p["startTime"] for p in perf.get("paint", []) if p["name"] == "first-contentful-paint"), None),
            "dom_complete": perf.get("navigation", {}).get("domComplete"),
            "long_tasks": perf["longTasks"],
        }
    finally:
        driver.quit()


def print_summary(results, target_url):
    """결과 요약을 출력합니다."""
    print(f"\n{'='*70}")
    print(f"SUMMARY - {target_url}")
    print(f"{'='*70}")
    print(f"{'Browser':<15} {'FPS(idle)':<10} {'FPS(scroll)':<12} {'FP(ms)':<8} {'FCP(ms)':<9} {'DOM(ms)':<9} {'LongTasks'}")
    print("-" * 70)
    for r in results:
        if "error" in r:
            print(f"{r['browser']:<15} ERROR: {r['error'][:50]}")
        else:
            fp = str(r["first_paint"] or "-")
            fcp = str(r["fcp"] or "-")
            dom = str(r["dom_complete"] or "-")
            print(f"{r['browser']:<15} {r['fps_idle']:<10} {r['fps_scroll']:<12} {fp:<8} {fcp:<9} {dom:<9} {r['long_tasks']}")


def save_result(results, target_url):
    """결과를 JSON 파일로 저장합니다."""
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(output_dir, f"fps_result_{timestamp}.json")

    output = {
        "timestamp": datetime.now().isoformat(),
        "target_url": target_url,
        "results": results,
    }
    with open(filename, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n결과 저장: {filename}")


def main():
    parser = argparse.ArgumentParser(description="AWS Device Farm 브라우저별 FPS 측정")
    parser.add_argument("--url", help="테스트할 URL (config.json 대신 사용)")
    parser.add_argument("--browser", help="특정 브라우저만 테스트 (chrome, firefox, MicrosoftEdge)")
    parser.add_argument("--setup", action="store_true", help="TestGrid 프로젝트 자동 생성")
    args = parser.parse_args()

    config = load_config()

    # 프로젝트 셋업
    if args.setup:
        setup_project()
        config = load_config()

    if not config.get("project_arn"):
        print("Error: config.json에 project_arn이 설정되지 않았습니다.")
        print("  1. config.json에 직접 입력하거나")
        print("  2. python browser_fps_test.py --setup 으로 자동 생성하세요.")
        sys.exit(1)

    target_url = args.url or config["target_url"]
    fps_duration_ms = config.get("fps_duration_seconds", 3) * 1000
    expires = config.get("session_expires_seconds", 300)

    # 브라우저 필터
    browsers = config["browsers"]
    if args.browser:
        browsers = [b for b in browsers if b["browserName"].lower() == args.browser.lower()]
        if not browsers:
            print(f"Error: '{args.browser}'는 지원하지 않는 브라우저입니다. (chrome, firefox, MicrosoftEdge)")
            sys.exit(1)

    # 세션 생성 및 테스트 실행
    print("Device Farm TestGrid 세션 생성 중...")
    hub_url = create_session(config["project_arn"], expires)
    print("세션 URL 발급 완료.\n")

    results = []
    for browser in browsers:
        try:
            result = run_fps_test(hub_url, browser, target_url, fps_duration_ms)
            results.append(result)
        except Exception as e:
            print(f"Error testing {browser['browserName']}: {e}")
            results.append({"browser": browser["browserName"], "error": str(e)})

    print_summary(results, target_url)
    save_result(results, target_url)


if __name__ == "__main__":
    main()
