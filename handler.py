import runpod
import os
import base64
import subprocess
import glob

# 컨테이너 시작 시 1회만 실행
model = load_model()  # global scope

def handler(job):
    # model은 이미 로드되어 있음
    result = model.inference(job["input"]["image_base64"])
    return result

def handler(job):
    """RunPod이 요청마다 호출하는 함수"""
    job_input = job["input"]
    
    # 1) 입력 이미지 받기 (base64로 받는 예시)
    image_b64 = job_input.get("image_base64")
    if not image_b64:
        return {"error": "image_base64 is required"}
    
    # 2) 임시 파일로 저장
    input_path = "/tmp/input_image.png"
    with open(input_path, "wb") as f:
        f.write(base64.b64decode(image_b64))
    
    # 3) inference_psd.py 실행
    result = subprocess.run(
        ["python", "inference/scripts/inference_psd.py",
         "--srcp", input_path,
         "--save_to_psd"],
        capture_output=True, text=True,
        cwd="/app/see-through"
    )
    
    if result.returncode != 0:
        return {"error": result.stderr}
    
    # 4) 결과 PSD 파일 찾기
    output_dir = "/app/see-through/workspace/layerdiff_output/"
    psd_files = glob.glob(os.path.join(output_dir, "*.psd"))
    
    if not psd_files:
        return {"error": "No PSD output found"}
    
    # 5) 결과를 base64로 반환 (또는 S3 업로드 후 URL 반환)
    with open(psd_files[0], "rb") as f:
        psd_b64 = base64.b64encode(f.read()).decode("utf-8")
    
    return {
        "psd_base64": psd_b64,
        "filename": os.path.basename(psd_files[0])
    }

# RunPod SDK 시작 — 이게 "서버" 역할을 함
runpod.serverless.start({"handler": handler})