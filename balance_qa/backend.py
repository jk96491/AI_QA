"""PyTorch 백엔드 설정 (학습 부분 공통).

- 장치는 CPU 고정 (DEVICE)
- 최적화기 수치(분포 평균·공분산·ES 파라미터)는 float64, 정책 신경망은 float32
- 병렬 워커는 torch 스레드 1개 (워커 수 × 스레드 수 과다 생성 방지)
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import torch

DEVICE = torch.device("cpu")
DTYPE = torch.float64          # 최적화기 내부 수치
POLICY_DTYPE = torch.float32   # 정책 신경망


def generator(seed: int) -> torch.Generator:
    """재현 가능한 CPU 난수 생성기."""
    g = torch.Generator(device="cpu")
    g.manual_seed(int(seed))
    return g


def as_tensor(x: Any, dtype: torch.dtype = DTYPE) -> torch.Tensor:
    if isinstance(x, torch.Tensor):
        return x.detach().to(device=DEVICE, dtype=dtype)
    return torch.as_tensor(np.asarray(x), dtype=dtype, device=DEVICE)


def to_numpy(x: Any) -> np.ndarray:
    if isinstance(x, torch.Tensor):
        return x.detach().cpu().numpy().astype(float)
    return np.asarray(x, dtype=float)


def configure_threads(n: Optional[int]) -> None:
    """메인 프로세스 torch 스레드 수 (None 이면 기본값 유지)."""
    if n:
        torch.set_num_threads(int(n))


def init_worker() -> None:
    """ProcessPoolExecutor 워커 초기화: 스레드 1개."""
    torch.set_num_threads(1)
