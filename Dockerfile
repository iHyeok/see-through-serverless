FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel

ENV PYTHONUNBUFFERED=1

# 모드 설정: pod(개발/테스트) 또는 serverless(프로덕션)
ARG MODE_TO_RUN=pod
ENV MODE_TO_RUN=$MODE_TO_RUN

# Network Volume의 HuggingFace 캐시를 사용
ENV HF_HOME=/runpod-volume/.cache/huggingface

WORKDIR /app

# 시스템 패키지
RUN apt-get update && apt-get install -y \
    git wget openssh-server \
    && rm -rf /var/lib/apt/lists/*

# see-through 레포 클론
RUN git clone https://github.com/shitagaki-lab/see-through.git
WORKDIR /app/see-through

# 심링크
RUN ln -sf common/assets assets

# 의존성 설치
RUN pip install --no-cache-dir -r requirements.txt

# RunPod SDK
RUN pip install --no-cache-dir runpod

# ★ 모델은 Network Volume에서 로드 (bake 불필요)
# /runpod-volume/.cache/huggingface/hub/ 에 이미 다운로드되어 있음

# handler, start.sh 복사
WORKDIR /app
COPY handler.py /app/handler.py
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]