"""결정 트리거용 작은 MLP 정책 (PyTorch, CPU).

입력: TriggerState 벡터 → 출력: (0, 1)^d (ParamSpace 로 실제 파라미터로 변환)
가중치는 평탄화된 1차원 벡터로 다뤄 진화 전략(ES)으로 학습한다.

병렬 워커로 보낼 때는 텐서 공유 메모리를 쓰지 않도록 (구조, 평탄 가중치 numpy) 로만 피클링한다.
"""
from __future__ import annotations

import math
from typing import Sequence, Tuple

import numpy as np
import torch
from torch import nn
from torch.nn.utils import parameters_to_vector, vector_to_parameters

from balance_qa.backend import DEVICE, DTYPE, POLICY_DTYPE, as_tensor, generator


def _rebuild(in_dim: int, out_dim: int, hidden: Tuple[int, ...], flat: np.ndarray) -> "MLPPolicy":
    pol = MLPPolicy(in_dim, out_dim, hidden, seed=0)
    pol.set_flat(flat)
    return pol


class MLPPolicy(nn.Module):
    def __init__(self, in_dim: int, out_dim: int, hidden: Sequence[int] = (16,), seed: int = 0) -> None:
        super().__init__()
        self.in_dim = in_dim
        self.out_dim = out_dim
        self.hidden = tuple(int(h) for h in hidden)
        sizes = [in_dim] + list(self.hidden) + [out_dim]
        layers = []
        for i, (a, b) in enumerate(zip(sizes[:-1], sizes[1:])):
            layers.append(nn.Linear(a, b))
            if i < len(sizes) - 2:
                layers.append(nn.Tanh())
        self.net = nn.Sequential(*layers).to(device=DEVICE, dtype=POLICY_DTYPE)
        self._init_weights(seed)
        self.requires_grad_(False)  # ES 는 그래디언트를 쓰지 않음

    def _init_weights(self, seed: int) -> None:
        g = generator(seed)
        linears = [m for m in self.net if isinstance(m, nn.Linear)]
        with torch.no_grad():
            for i, lin in enumerate(linears):
                std = 1.0 / math.sqrt(lin.in_features)
                # 마지막 층은 작게 시작 → 초기 출력이 bias 로 정한 기본값 근처
                if i == len(linears) - 1:
                    std *= 0.1
                lin.weight.normal_(0.0, std, generator=g)
                lin.bias.zero_()

    @property
    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters())

    # ----- 평탄 가중치 -----
    def get_flat(self) -> torch.Tensor:
        return parameters_to_vector(self.parameters()).detach().to(DTYPE).clone()

    def set_flat(self, theta) -> None:
        t = as_tensor(theta, POLICY_DTYPE)
        if t.shape != (self.n_params,):
            raise ValueError("expected %d params, got %s" % (self.n_params, tuple(t.shape)))
        with torch.no_grad():
            vector_to_parameters(t, self.parameters())

    def with_flat(self, theta) -> "MLPPolicy":
        return _rebuild(self.in_dim, self.out_dim, self.hidden, as_tensor(theta).numpy())

    def set_output_bias(self, target_unit) -> None:
        """출력층 bias 를 logit(target) 으로 설정해 초기 출력을 기본 파라미터에 맞춘다."""
        t = as_tensor(np.clip(np.asarray(target_unit, dtype=float), 0.02, 0.98), POLICY_DTYPE)
        last = [m for m in self.net if isinstance(m, nn.Linear)][-1]
        with torch.no_grad():
            last.bias.copy_(torch.log(t / (1.0 - t)))

    # ----- 추론 -----
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.net(x))

    def act(self, x: np.ndarray) -> np.ndarray:
        """numpy 입력 → numpy 출력 (시뮬레이터 쪽 인터페이스)."""
        with torch.no_grad():
            out = self.forward(as_tensor(x, POLICY_DTYPE))
        return out.numpy().astype(float)

    # ----- 피클링 (워커 전송) -----
    def __reduce__(self):
        return (_rebuild, (self.in_dim, self.out_dim, self.hidden, self.get_flat().numpy()))

    def __repr__(self) -> str:
        sizes = [self.in_dim] + list(self.hidden) + [self.out_dim]
        return "MLPPolicy(%s, params=%d, torch-cpu)" % ("-".join(map(str, sizes)), self.n_params)
