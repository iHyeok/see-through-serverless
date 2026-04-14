"""
see-through-serverless 테스트 스크립트

사용법:
  python test_script.py                          # 기본 설정으로 테스트
  python test_script.py --image my_image.png     # 이미지 지정
  python test_script.py --resolution 1536        # 해상도 변경
  python test_script.py --include_layers         # 분할 이미지 zip도 받기
"""

import argparse
import requests
import base64
import time
import os


def main():
    parser = argparse.ArgumentParser(description="see-through-serverless 테스트")
    parser.add_argument("--image", type=str, default="test_image.png", help="입력 이미지 경로")
    parser.add_argument("--api_key", type=str, default=None, help="RunPod API Key (또는 RUNPOD_API_KEY 환경변수)")
    parser.add_argument("--endpoint_id", type=str, default=None, help="Endpoint ID (또는 RUNPOD_ENDPOINT_ID 환경변수)")
    parser.add_argument("--resolution", type=int, default=1280, help="LayerDiff 추론 해상도 (기본: 1280)")
    parser.add_argument("--resolution_depth", type=int, default=768, help="Depth 모델 해상도 (기본: 768)")
    parser.add_argument("--inference_steps", type=int, default=30, help="디노이징 스텝 수 (기본: 30)")
    parser.add_argument("--seed", type=int, default=42, help="랜덤 시드 (기본: 42)")
    parser.add_argument("--no_tblr_split", action="store_true", help="좌우 분리 비활성화")
    parser.add_argument("--include_layers", action="store_true", help="분할 이미지 zip 포함")
    parser.add_argument("--output_dir", type=str, default=".", help="결과 저장 경로 (기본: 현재 디렉토리)")
    parser.add_argument("--poll_interval", type=int, default=10, help="폴링 간격 초 (기본: 10)")
    args = parser.parse_args()

    # API Key / Endpoint ID
    api_key = args.api_key or os.environ.get("RUNPOD_API_KEY")
    endpoint_id = args.endpoint_id or os.environ.get("RUNPOD_ENDPOINT_ID")

    if not api_key:
        print("Error: --api_key 또는 RUNPOD_API_KEY 환경변수를 설정해주세요.")
        return
    if not endpoint_id:
        print("Error: --endpoint_id 또는 RUNPOD_ENDPOINT_ID 환경변수를 설정해주세요.")
        return

    # 이미지 로드
    if not os.path.exists(args.image):
        print(f"Error: 이미지 파일을 찾을 수 없습니다: {args.image}")
        return

    with open(args.image, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    print(f"Image: {args.image} ({len(image_b64) // 1024} KB base64)")
    print(f"Resolution: {args.resolution}")
    print(f"Resolution Depth: {args.resolution_depth}")
    print(f"Inference Steps: {args.inference_steps}")
    print(f"Seed: {args.seed}")
    print(f"TBLR Split: {not args.no_tblr_split}")
    print(f"Include Layers: {args.include_layers}")
    print()

    # 요청 제출
    payload = {
        "input": {
            "image_base64": image_b64,
            "resolution": args.resolution,
            "resolution_depth": args.resolution_depth,
            "inference_steps": args.inference_steps,
            "seed": args.seed,
            "tblr_split": not args.no_tblr_split,
            "include_layers": args.include_layers,
        }
    }

    headers = {"Authorization": f"Bearer {api_key}"}
    base_url = f"https://api.runpod.ai/v2/{endpoint_id}"

    print("Submitting job...")
    res = requests.post(f"{base_url}/run", headers=headers, json=payload)

    if res.status_code != 200:
        print(f"Error: HTTP {res.status_code} - {res.text}")
        return

    job_data = res.json()
    job_id = job_data["id"]
    print(f"Job ID: {job_id}")
    print(f"Status: {job_data['status']}")
    print()

    # 결과 폴링
    start_time = time.time()

    while True:
        status_res = requests.get(
            f"{base_url}/status/{job_id}",
            headers=headers
        ).json()

        elapsed = time.time() - start_time
        current_status = status_res["status"]
        print(f"[{elapsed:.0f}s] Status: {current_status}")

        if current_status == "COMPLETED":
            output = status_res["output"]

            # PSD 저장
            os.makedirs(args.output_dir, exist_ok=True)
            psd_filename = output.get("filename", "result.psd")
            psd_path = os.path.join(args.output_dir, psd_filename)

            psd_data = base64.b64decode(output["psd_base64"])
            with open(psd_path, "wb") as f:
                f.write(psd_data)
            print(f"\nPSD saved: {psd_path} ({len(psd_data) // 1024} KB)")

            # 레이어 zip 저장
            if "layers_zip_base64" in output:
                zip_filename = output.get("layers_zip_filename", "layers.zip")
                zip_path = os.path.join(args.output_dir, zip_filename)

                zip_data = base64.b64decode(output["layers_zip_base64"])
                with open(zip_path, "wb") as f:
                    f.write(zip_data)
                print(f"Layers ZIP saved: {zip_path} ({len(zip_data) // 1024} KB)")

            if "layers_zip_error" in output:
                print(f"Layers ZIP error: {output['layers_zip_error']}")

            print(f"\nTotal time: {elapsed:.1f}s")
            break

        elif current_status == "FAILED":
            print(f"\nFailed: {status_res.get('output') or status_res.get('error')}")
            break

        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()