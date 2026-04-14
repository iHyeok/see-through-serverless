import os
import sys
import base64
import subprocess
import glob
import json
import shutil

# Network Volume의 HuggingFace 캐시 경로 설정
if os.path.exists("/runpod-volume/.cache/huggingface"):
    os.environ["HF_HOME"] = "/runpod-volume/.cache/huggingface"
elif os.path.exists("/workspace/.cache/huggingface"):
    os.environ["HF_HOME"] = "/workspace/.cache/huggingface"

SEETHROUGH_DIR = "/app/see-through"
OUTPUT_DIR = os.path.join(SEETHROUGH_DIR, "workspace/layerdiff_output/")

mode_to_run = os.getenv("MODE_TO_RUN", "pod")


def handler(job):
    """RunPod이 요청마다 호출하는 함수"""
    job_input = job["input"]

    # 1) 입력 파라미터
    image_b64 = job_input.get("image_base64")
    if not image_b64:
        return {"error": "image_base64 is required"}

    resolution = job_input.get("resolution", 1280)
    resolution_depth = job_input.get("resolution_depth", 768)
    inference_steps = job_input.get("inference_steps", 30)
    seed = job_input.get("seed", 42)
    tblr_split = job_input.get("tblr_split", True)
    include_layers = job_input.get("include_layers", False)  # 분할 이미지 zip 포함 여부

    # 2) 임시 파일로 저장
    input_path = "/tmp/input_image.png"
    with open(input_path, "wb") as f:
        f.write(base64.b64decode(image_b64))

    # 3) 이전 결과 정리
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for old_file in glob.glob(os.path.join(OUTPUT_DIR, "*.psd")):
        os.remove(old_file)
    for old_dir in glob.glob(os.path.join(OUTPUT_DIR, "*/")):
        shutil.rmtree(old_dir, ignore_errors=True)

    # 4) inference_psd.py 실행
    cmd = [
        "python", "inference/scripts/inference_psd.py",
        "--srcp", input_path,
        "--save_to_psd",
        "--resolution", str(resolution),
        "--resolution_depth", str(resolution_depth),
        "--inference_steps", str(inference_steps),
        "--seed", str(seed),
        "--disable_progressbar",
    ]
    if tblr_split:
        cmd.append("--tblr_split")

    env = os.environ.copy()
    result = subprocess.run(
        cmd,
        capture_output=True, text=True,
        cwd=SEETHROUGH_DIR,
        env=env
    )

    if result.returncode != 0:
        return {"error": result.stderr[-1000:]}

    # 5) 결과 PSD 파일 찾기 (_depth 제외)
    psd_files = [
        f for f in glob.glob(os.path.join(OUTPUT_DIR, "*.psd"))
        if "_depth" not in os.path.basename(f)
    ]
    if not psd_files:
        psd_files = glob.glob(os.path.join(OUTPUT_DIR, "*.psd"))
    if not psd_files:
        return {"error": "No PSD output found", "stdout": result.stdout[-500:]}

    # 6) PSD를 base64로
    psd_path = psd_files[0]
    with open(psd_path, "rb") as f:
        psd_b64 = base64.b64encode(f.read()).decode("utf-8")

    filename = os.path.basename(psd_path)

    response = {
        "psd_base64": psd_b64,
        "filename": filename,
    }

    # 7) 분할 이미지 zip (옵션)
    if include_layers:
        # PSD와 동일한 이름의 폴더 찾기
        psd_stem = os.path.splitext(psd_path)[0]  # 확장자 제거한 경로
        layers_dir = psd_stem  # 동일 이름 폴더

        if os.path.isdir(layers_dir):
            zip_path = f"/tmp/{os.path.basename(layers_dir)}_layers"
            shutil.make_archive(zip_path, "zip", layers_dir)
            zip_path = zip_path + ".zip"

            with open(zip_path, "rb") as f:
                zip_b64 = base64.b64encode(f.read()).decode("utf-8")

            response["layers_zip_base64"] = zip_b64
            response["layers_zip_filename"] = os.path.basename(zip_path)

            os.remove(zip_path)
        else:
            response["layers_zip_error"] = f"Layers directory not found: {os.path.basename(layers_dir)}"

    # 8) 정리
    for f_path in glob.glob(os.path.join(OUTPUT_DIR, "*.psd")):
        os.remove(f_path)
    for old_dir in glob.glob(os.path.join(OUTPUT_DIR, "*/")):
        shutil.rmtree(old_dir, ignore_errors=True)

    return response


if mode_to_run == "pod":
    # --- Pod 모드: 로컬 테스트 ---
    print("Running in Pod mode (local test)")
    print(f"HF_HOME: {os.environ.get('HF_HOME', 'not set')}")

    test_image = os.path.join(SEETHROUGH_DIR, "assets/test_image.png")
    if not os.path.exists(test_image):
        print(f"Test image not found: {test_image}")
        sys.exit(1)

    with open(test_image, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    fake_job = {"input": {"image_base64": img_b64, "include_layers": True}}
    result = handler(fake_job)

    display = dict(result)
    if "psd_base64" in display:
        display["psd_base64"] = display["psd_base64"][:100] + "...(truncated)"
    if "layers_zip_base64" in display:
        display["layers_zip_base64"] = display["layers_zip_base64"][:100] + "...(truncated)"
    print(json.dumps(display, indent=2, ensure_ascii=False))

else:
    # --- Serverless 모드 ---
    import runpod
    print("Running in Serverless mode")
    print(f"HF_HOME: {os.environ.get('HF_HOME', 'not set')}")
    runpod.serverless.start({"handler": handler})