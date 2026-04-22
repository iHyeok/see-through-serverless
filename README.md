# see-through-serverless

[See-through](https://github.com/shitagaki-lab/see-through) (SIGGRAPH 2026)를 RunPod Serverless로 배포하기 위한 래퍼.

애니메 캐릭터 이미지를 입력하면, 최대 24개 시맨틱 레이어로 분해된 PSD 파일을 반환합니다.
결과 파일은 Cloudflare R2에 업로드되고, 다운로드 URL이 반환됩니다.

## API

### Endpoint

```
POST https://api.runpod.ai/v2/{ENDPOINT_ID}/run
Authorization: Bearer {RUNPOD_API_KEY}
```

### 요청

```json
{
  "input": {
    "image_base64": "(필수) PNG/JPG 이미지의 base64 문자열",
    "resolution": 1280,
    "resolution_depth": 768,
    "inference_steps": 30,
    "seed": 42,
    "tblr_split": true,
    "include_layers": false
  }
}
```

### 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `image_base64` | string | (필수) | 입력 이미지의 base64 인코딩 |
| `resolution` | int | 1280 | LayerDiff 추론 해상도. 높을수록 디테일 증가, 시간/VRAM 소모 증가 |
| `resolution_depth` | int | 768 | Depth 모델 해상도. 학습 시 768로 훈련됨. -1로 설정하면 resolution과 동일하게 적용 |
| `inference_steps` | int | 30 | 디노이징 스텝 수. 높을수록 품질 향상, 시간 증가 |
| `seed` | int | 42 | 랜덤 시드. 동일 입력 + 동일 시드 = 동일 결과 |
| `tblr_split` | bool | true | 좌우 대칭 파츠(눈, 귀, 핸드웨어 등)를 좌/우로 분리 |
| `include_layers` | bool | false | true로 설정 시 분할된 레이어 이미지들을 zip으로 압축하여 R2에 업로드 |

### 응답

**기본 (include_layers = false)**

```json
{
  "psd_url": "https://pub-xxx.r2.dev/jobs/{job_id}/input_image.psd",
  "filename": "input_image.psd"
}
```

**레이어 포함 (include_layers = true)**

```json
{
  "psd_url": "https://pub-xxx.r2.dev/jobs/{job_id}/input_image.psd",
  "filename": "input_image.psd",
  "layers_zip_url": "https://pub-xxx.r2.dev/jobs/{job_id}/input_image_layers.zip",
  "layers_zip_filename": "input_image_layers.zip"
}
```

**실패 시**

```json
{
  "error": "에러 메시지"
}
```

### 결과 조회

비동기 요청이므로 job ID로 결과를 폴링합니다.

```
GET https://api.runpod.ai/v2/{ENDPOINT_ID}/status/{JOB_ID}
Authorization: Bearer {RUNPOD_API_KEY}
```

status 값: `IN_QUEUE` → `IN_PROGRESS` → `COMPLETED` 또는 `FAILED`

## 테스트

```bash
# 환경변수 설정
export RUNPOD_API_KEY=your_key
export RUNPOD_ENDPOINT_ID=your_endpoint_id

# 기본 테스트 (URL만 출력)
python test_script.py --image test_image.png

# 결과 파일 자동 다운로드
python test_script.py --image test_image.png --download

# 해상도 변경 + 레이어 zip 포함 + 다운로드
python test_script.py --image test_image.png --resolution 1536 --include_layers --download

# 결과를 특정 폴더에 저장
python test_script.py --image test_image.png --download --output_dir ./results

# 모든 옵션 보기
python test_script.py --help
```

## 환경변수 (RunPod Endpoint)

| Key | 설명 |
|---|---|
| `MODE_TO_RUN` | `serverless` (필수) |
| `R2_ACCESS_KEY_ID` | Cloudflare R2 Access Key ID |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 Secret Access Key |
| `R2_ENDPOINT_URL` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `R2_BUCKET_NAME` | R2 bucket 이름 |
| `R2_PUBLIC_URL` | R2 공개 URL (예: `https://pub-xxx.r2.dev`) |

## 프로젝트 구조

```
see-through-serverless/
├── Dockerfile      # PyTorch 2.8.0 + CUDA 12.4 베이스, see-through 환경 구축
├── handler.py      # RunPod Serverless handler (dual-mode: pod/serverless)
├── start.sh        # 컨테이너 entrypoint (모드별 분기)
├── test_script.py  # 로컬 테스트 스크립트
└── README.md
```

## 배포

RunPod GitHub 연동을 통해 자동 빌드/배포됩니다.
코드 수정 후 GitHub Release를 생성하면 재빌드가 트리거됩니다.