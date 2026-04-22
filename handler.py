import os
import sys
import base64
import subprocess
import glob
import json
import shutil
import uuid
import boto3

# Network Volume의 HuggingFace 캐시 경로 설정
if os.path.exists("/runpod-volume/.cache/huggingface"):
    os.environ["HF_HOME"] = "/runpod-volume/.cache/huggingface"
elif os.path.exists("/workspace/.cache/huggingface"):
    os.environ["HF_HOME"] = "/workspace/.cache/huggingface"

SEETHROUGH_DIR = "/app/see-through"
OUTPUT_DIR = os.path.join(SEETHROUGH_DIR, "workspace/layerdiff_output/")

mode_to_run = os.getenv("MODE_TO_RUN", "pod")

# R2 설정
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL", "")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "")  # https://pub-xxx.r2.dev


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT_URL,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    )


def upload_to_r2(local_path, r2_key):
    """파일을 R2에 업로드하고 공개 URL을 반환"""
    s3 = get_s3_client()

    # Content-Type 설정
    ext = os.path.splitext(local_path)[1].lower()
    content_types = {
        ".psd": "application/octet-stream",
        ".zip": "application/zip",
        ".png": "image/png",
    }
    content_type = content_types.get(ext, "application/octet-stream")

    s3.upload_file(
        local_path,
        R2_BUCKET_NAME,
        r2_key,
        ExtraArgs={"ContentType": content_type},
    )

    # 공개 URL
    public_url = f"{R2_PUBLIC_URL.rstrip('/')}/{r2_key}"
    return public_url


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
    include_layers = job_input.get("include_layers", False)

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

    psd_path = psd_files[0]
    filename = os.path.basename(psd_path)

    # 6) R2에 업로드
    job_id = job.get("id", uuid.uuid4().hex[:8])
    r2_prefix = f"jobs/{job_id}"

    try:
        psd_url = upload_to_r2(psd_path, f"{r2_prefix}/{filename}")
    except Exception as e:
        return {"error": f"R2 upload failed: {str(e)}"}

    response = {
        "psd_url": psd_url,
        "filename": filename,
    }

    # 7) 분할 이미지 zip (옵션)
    if include_layers:
        psd_stem = os.path.splitext(psd_path)[0]
        layers_dir = psd_stem

        if os.path.isdir(layers_dir):
            zip_base = f"/tmp/{os.path.basename(layers_dir)}_layers"
            shutil.make_archive(zip_base, "zip", layers_dir)
            zip_path = zip_base + ".zip"
            zip_filename = os.path.basename(zip_path)

            try:
                zip_url = upload_to_r2(zip_path, f"{r2_prefix}/{zip_filename}")
                response["layers_zip_url"] = zip_url
                response["layers_zip_filename"] = zip_filename
            except Exception as e:
                response["layers_zip_error"] = f"R2 upload failed: {str(e)}"

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
    print(f"R2_BUCKET: {R2_BUCKET_NAME}")
    print(f"R2_PUBLIC_URL: {R2_PUBLIC_URL}")

    test_image = os.path.join(SEETHROUGH_DIR, "assets/test_image.png")
    if not os.path.exists(test_image):
        print(f"Test image not found: {test_image}")
        sys.exit(1)

    with open(test_image, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    fake_job = {"id": "test-001", "input": {"image_base64": img_b64, "include_layers": True}}
    result = handler(fake_job)
    print(json.dumps(result, indent=2, ensure_ascii=False))

else:
    # --- Serverless 모드 ---
    import runpod
    print("Running in Serverless mode")
    print(f"HF_HOME: {os.environ.get('HF_HOME', 'not set')}")
    print(f"R2_BUCKET: {R2_BUCKET_NAME}")
    runpod.serverless.start({"handler": handler})