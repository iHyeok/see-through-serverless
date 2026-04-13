FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel

ENV PYTHONUNBUFFERED=1

ARG MODE_TO_RUN=pod
ENV MODE_TO_RUN=$MODE_TO_RUN

WORKDIR /app

# 시스템 패키지
RUN apt-get update && apt-get install -y \
    git wget openssh-server libgl1-mesa-glx libglib2.0-0 \
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

# 모델 weights bake
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('layerdifforg/seethroughv0.0.2_layerdiff3d')"
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('24yearsold/seethroughv0.0.1_marigold')"

# handler, start.sh 복사
WORKDIR /app
COPY handler.py /app/handler.py
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]