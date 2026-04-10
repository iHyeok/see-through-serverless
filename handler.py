import os
import sys
import base64
import subprocess
import glob
import json

SEETHROUGH_DIR = "/app/see-through"
OUTPUT_DIR = os.path.join(SEETHROUGH_DIR, "workspace/layerdiff_output/")

mode_to_run = os.getenv("MODE_TO_RUN", "pod")


def handler(job):
    """RunPod이 요청마다 호출하는 함수"""
    job_input = job["input"]

    # 1) 입력 이미지 받기
    image_b64 = job_input.get("image_base64")
    if not image_b64:
        return {"error": "image_base64 is required"}

    # 2) 임시 파일로 저장
    input_path = "/tmp/input_image.png"
    with open(input_path, "wb") as f:
        f.write(base64.b64decode(image_b64))

    # 3) 이전 결과 정리 (같은 worker가 재사용될 때 꼬임 방지)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for old_file in glob.glob(os.path.join(OUTPUT_DIR, "*.psd")):
        os.remove(old_file)

    # 4) inference_psd.py 실행
    result = subprocess.run(
        ["python", "inference/scripts/inference_psd.py",
         "--srcp", input_path,
         "--save_to_psd"],
        capture_output=True, text=True,
        cwd=SEETHROUGH_DIR
    )

    if result.returncode != 0:
        return {"error": result.stderr[-1000:]}

    # 5) 결과 PSD 파일 찾기 (_depth 제외, 메인 PSD만)
    psd_files = [
        f for f in glob.glob(os.path.join(OUTPUT_DIR, "*.psd"))
        if "_depth" not in os.path.basename(f)
    ]

    if not psd_files:
        # depth만 있으면 그거라도 반환
        psd_files = glob.glob(os.path.join(OUTPUT_DIR, "*.psd"))

    if not psd_files:
        return {"error": "No PSD output found", "stdout": result.stdout[-500:]}

    # 6) 결과를 base64로 반환
    psd_path = psd_files[0]
    with open(psd_path, "rb") as f:
        psd_b64 = base64.b64encode(f.read()).decode("utf-8")

    filename = os.path.basename(psd_path)

    # 7) 정리
    for f_path in glob.glob(os.path.join(OUTPUT_DIR, "*.psd")):
        os.remove(f_path)

    return {
        "psd_base64": psd_b64,
        "filename": filename
    }


if mode_to_run == "pod":
    # --- Pod 모드: 로컬 테스트 ---
    print("Running in Pod mode (local test)")

    test_image = os.path.join(SEETHROUGH_DIR, "assets/test_image.png")
    if not os.path.exists(test_image):
        print(f"Test image not found: {test_image}")
        sys.exit(1)

    with open(test_image, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    fake_job = {"input": {"image_base64": img_b64}}
    result = handler(fake_job)

    # 결과 출력 (base64는 앞부분만)
    display = dict(result)
    if "psd_base64" in display:
        display["psd_base64"] = display["psd_base64"][:100] + "...(truncated)"
    print(json.dumps(display, indent=2, ensure_ascii=False))

else:
    # --- Serverless 모드 ---
    import runpod
    print("Running in Serverless mode")
    runpod.serverless.start({"handler": handler})